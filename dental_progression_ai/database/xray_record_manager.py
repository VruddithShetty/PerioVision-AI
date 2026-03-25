import datetime
from database.mongodb_connection import MongoDBConnection

class XrayRecordManager:
    def __init__(self):
        self.db = MongoDBConnection.get_db()
        self.collection = self.db["xray_records"]
        self.collection.create_index("record_id", unique=True)
        self.collection.create_index("patient_id")

    def create_record(self, record_id, patient_id, xray_image_path, analysis_date=None,
                      bone_loss_results=None, risk_prediction=None,
                      landmark_coordinates=None, bone_loss_metrics=None,
                      progression_velocity=None, prediction_results=None):
        if analysis_date is None:
            analysis_date = datetime.datetime.now().strftime("%Y-%m-%d")
        if bone_loss_results is None:
            bone_loss_results = {}

        record_document = {
            "record_id": record_id,
            "patient_id": int(patient_id),
            "xray_image_path": xray_image_path,
            "analysis_date": analysis_date,
            # Legacy fields kept for backward-compat
            "bone_loss_results": bone_loss_results,
            "risk_prediction": risk_prediction,
            # TALPA extended fields
            "landmark_coordinates": landmark_coordinates or {},
            "bone_loss_metrics": bone_loss_metrics or {},
            "progression_velocity": progression_velocity or {},
            "prediction_results": prediction_results or {},
        }
        self.collection.insert_one(record_document)
        return record_document

    def get_records_by_patient(self, patient_id):
        # Sort by analysis date ascending
        patient_id = int(patient_id)
        records = list(self.collection.find({"patient_id": patient_id}, {"_id": 0}).sort("analysis_date", 1))
        return records

    def get_record(self, record_id):
        return self.collection.find_one({"record_id": record_id}, {"_id": 0})
