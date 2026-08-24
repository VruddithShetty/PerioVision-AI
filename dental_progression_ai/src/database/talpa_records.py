import datetime
from database.connection import db

class ToothBoneLossRecord:
    """
    Data model representing a single surface-specific periodontal bone loss
    measurement derived from landmark coordinates and alignment transforms.
    """
    def __init__(self, patient_id, tooth_id, surface, radiograph_date, bone_loss_percentage,
                 cej_bonecrest_distance_px=None, cej_apex_distance_px=None,
                 landmark_confidence=1.0, alignment_transform_id=None):
        self.patient_id = int(patient_id)
        self.tooth_id = int(tooth_id)
        self.surface = str(surface).lower()  # mesial/distal/buccal/lingual
        self.radiograph_date = str(radiograph_date)  # ISO "YYYY-MM-DD"
        self.bone_loss_percentage = float(bone_loss_percentage)
        self.cej_bonecrest_distance_px = float(cej_bonecrest_distance_px) if cej_bonecrest_distance_px is not None else None
        self.cej_apex_distance_px = float(cej_apex_distance_px) if cej_apex_distance_px is not None else None
        self.landmark_confidence = float(landmark_confidence)
        self.alignment_transform_id = str(alignment_transform_id) if alignment_transform_id is not None else None

    def to_dict(self):
        return {
            "patient_id": self.patient_id,
            "tooth_id": self.tooth_id,
            "surface": self.surface,
            "radiograph_date": self.radiograph_date,
            "bone_loss_percentage": self.bone_loss_percentage,
            "cej_bonecrest_distance_px": self.cej_bonecrest_distance_px,
            "cej_apex_distance_px": self.cej_apex_distance_px,
            "landmark_confidence": self.landmark_confidence,
            "alignment_transform_id": self.alignment_transform_id
        }

class TalpaRecordManager:
    """
    Database query layer for TALPA tooth bone loss records, managing
    chronologically sorted historical series and handling missing data / single point cases.
    """
    def __init__(self):
        self.collection = db["tooth_bone_loss_records"]

    def insert_record(self, record: ToothBoneLossRecord):
        doc = record.to_dict()
        self.collection.insert_one(doc)
        return doc

    def get_time_series(self, patient_id, tooth_id, surface=None):
        """
        Retrieves the full time series of ToothBoneLossRecords for a given patient_id + tooth_id,
        sorted chronologically.
        """
        query = {
            "patient_id": int(patient_id),
            "tooth_id": int(tooth_id)
        }
        if surface:
            query["surface"] = str(surface).lower()

        # Sort ascending (oldest first)
        docs = list(self.collection.find(query, {"_id": 0}).sort("radiograph_date", 1))

        if not docs:
            return {
                "status": "insufficient_data",
                "message": f"No records found for patient {patient_id}, tooth {tooth_id}",
                "records": []
            }

        if len(docs) < 2:
            return {
                "status": "insufficient_data",
                "message": f"Only one visit record available for patient {patient_id}, tooth {tooth_id}. Velocity cannot be computed.",
                "records": docs
            }

        return {
            "status": "success",
            "records": docs
        }

    def compute_and_save_patient_talpa_summary(self, patient_id):
        """
        Groups all bone loss records for a patient, computes TALPA velocity/trend
        profiles per site, aggregates them into a full-mouth summary, and
        stores it in the 'progression_summary' collection.
        """
        all_records = list(self.collection.find({"patient_id": int(patient_id)}, {"_id": 0}))
        if not all_records:
            return {
                "status": "insufficient_data",
                "message": "No historical bone loss records found for patient"
            }

        grouped = {}
        for r in all_records:
            tooth_id = r["tooth_id"]
            surf = r["surface"]
            grouped.setdefault(tooth_id, {}).setdefault(surf, []).append(r)

        # Actually use real ProgressionVelocityCalculator
        from analysis.progression_velocity_calculator import ProgressionVelocityCalculator
        calc = ProgressionVelocityCalculator()

        per_site_profiles = {}
        overall_max_velocity = 0.0
        overall_trend = "stable"
        rapid_progression_sites = []

        for tooth_id, surfaces in grouped.items():
            for surf, measurements in surfaces.items():
                profile = calc.compute_talpa_profile(measurements)
                site_key = f"{tooth_id}_{surf}"
                per_site_profiles[site_key] = profile

                if profile["status"] == "success":
                    v = profile["velocity"]
                    if v > overall_max_velocity:
                        overall_max_velocity = v

                    tc = profile["trend"]["trend_classification"]
                    if tc in ["rapid progression", "accelerating"]:
                        overall_trend = "rapid progression"
                        rapid_progression_sites.append(site_key)
                    elif tc == "slow progression" and overall_trend not in ["rapid progression", "accelerating"]:
                        overall_trend = "slow progression"
                    elif tc == "improving" and overall_trend == "stable":
                        overall_trend = "improving"

        summary_doc = {
            "patient_id": int(patient_id),
            "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "overall_max_velocity_mm_yr": round(overall_max_velocity, 4),
            "overall_trend": overall_trend,
            "rapid_progression_sites": rapid_progression_sites,
            "per_site_profiles": per_site_profiles,
            "input_data_version": "v1.0.0"
        }

        db["progression_summary"].update_one(
            {"patient_id": int(patient_id)},
            {"$set": summary_doc},
            upsert=True
        )

        return summary_doc
