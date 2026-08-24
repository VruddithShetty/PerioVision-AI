from database.connection import db

def get_next_patient_id() -> int:
    """
    Queries the patients collection for the maximum patient_id and returns max+1.
    Starts at 1001 if no patients exist.
    """
    collection = db["patients"]
    last_patient = collection.find_one(sort=[("patient_id", -1)])
    if last_patient and "patient_id" in last_patient:
        return last_patient["patient_id"] + 1
    return 1001
