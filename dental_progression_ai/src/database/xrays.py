import datetime
import os
import cv2
import numpy as np
from database.connection import db
from security.watermark import XRayWatermarker
from security.rbac import RBACEnforcer
from core.preprocessing import compute_phash

class XrayRecordManager:
    """
    Manages clinical radiograph records with cryptographic provenance and RBAC.
    """
    
    def __init__(self):
        self.rbac = RBACEnforcer()
        self.collection = db["xray_records"]

    def _generate_record_id(self) -> str:
        now = datetime.datetime.now(datetime.timezone.utc)
        date_str = now.strftime("%Y%m%d")
        count = self.collection.count_documents({
            "record_id": {"$regex": f"^XR{date_str}"}
        })
        return f"XR{date_str}{count + 1:03d}"

    def _normalize_analysis_result(self, analysis_result_dict):
        """Normalize analysis payloads into per-tooth dictionaries."""
        if isinstance(analysis_result_dict, dict) and "teeth" in analysis_result_dict:
            normalized = {}
            for tooth in analysis_result_dict.get("teeth", []):
                tooth_id = tooth.get("tooth_id")
                if tooth_id is None:
                    continue
                normalized[str(tooth_id)] = {
                    "bone_loss_pct": float(tooth.get("bone_loss_pct", 0.0) or 0.0),
                    "severity": tooth.get("severity", "Unknown"),
                    "velocity_per_year": tooth.get("velocity_per_year"),
                    "talpa_grade": tooth.get("talpa_grade"),
                    "risk_level": tooth.get("risk_level"),
                }
            return normalized

        if isinstance(analysis_result_dict, list):
            normalized = {}
            for tooth in analysis_result_dict:
                tooth_id = tooth.get("tooth_id")
                if tooth_id is None:
                    continue
                normalized[str(tooth_id)] = dict(tooth)
            return normalized

        return analysis_result_dict if isinstance(analysis_result_dict, dict) else {}

    def create_record(
        self,
        record_id,
        patient_id,
        image_path,
        analysis_date,
        bone_loss_results,
        predictions,
        annotated_path=None,
        report_path=None,
        dicom_metadata=None,
        analysis_payload=None,
    ):
        """Create a persisted X-ray record using the repository contract."""
        watermarker = XRayWatermarker()
        img = cv2.imread(image_path)
        if img is None:
            if os.environ.get("TESTING") == "True" or os.environ.get("DB_MODE") == "demo":
                img = np.zeros((512, 512, 3), dtype=np.uint8)
            else:
                raise FileNotFoundError(f"Could not read image at {image_path}")

        watermarked_img, signature = watermarker.embed_watermark(img, record_id)
        cv2.imwrite(image_path, watermarked_img)
        image_hash = compute_phash(image_path)

        normalized_analysis = self._normalize_analysis_result(analysis_payload or bone_loss_results)
        document = {
            "record_id": record_id,
            "patient_id": int(patient_id),
            "image_path": image_path,
            "analysis_date": analysis_date,
            "analysis_result": normalized_analysis,
            "bone_loss_results": bone_loss_results,
            "predictions": predictions,
            "signature_hash": signature,
            "perceptual_hash": image_hash,
            "integrity_status": "VERIFIED",
        }
        if annotated_path:
            document["annotated_path"] = annotated_path
        if report_path:
            document["report_path"] = report_path
        if dicom_metadata:
            document["dicom_metadata"] = dicom_metadata

        self.collection.insert_one(document)
        return record_id

    def save_record(self, patient_id, image_path, analysis_result_dict):
        record_id = self._generate_record_id()
        return self.create_record(
            record_id=record_id,
            patient_id=patient_id,
            image_path=image_path,
            analysis_date=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            bone_loss_results=analysis_result_dict,
            predictions={},
            analysis_payload=analysis_result_dict,
        )

    def update_record_fields(self, record_id, fields_dict):
        """Update a record with additional metadata fields."""
        if not fields_dict:
            return False
        result = self.collection.update_one({"record_id": record_id}, {"$set": fields_dict})
        return result.modified_count > 0

    def get_records_by_patient(self, patient_id, requester_id=None, requester_role="doctor"):
        base_query = {"patient_id": int(patient_id)}
        rbac_query = self.rbac.filter_query_by_role(requester_id, requester_role, "xray_records", base_query)
        return list(self.collection.find(rbac_query, {"_id": 0}).sort("analysis_date", 1))

    def get_latest_record_for_patient(self, patient_id, requester_id=None, requester_role="doctor"):
        """Return the most recent X-ray record for a patient."""
        records = self.get_records_by_patient(patient_id, requester_id, requester_role)
        return records[-1] if records else None

    def get_records_with_report_path(self, requester_id=None, requester_role="doctor"):
        """Return all records that already have a stored report path."""
        base_query = {"report_path": {"$exists": True, "$ne": None}}
        rbac_query = self.rbac.filter_query_by_role(requester_id, requester_role, "xray_records", base_query)
        return list(self.collection.find(rbac_query, {"_id": 0}).sort("analysis_date", -1))

    def get_record(self, record_id, requester_id=None, requester_role="doctor"):
        doc = self.collection.find_one({"record_id": record_id}, {"_id": 0})
        if not doc: return None
        patient_doc = db["patients"].find_one({"patient_id": doc["patient_id"]})
        if not self.rbac.enforce_patient_access(requester_id, requester_role, patient_doc):
            return None
        return doc
