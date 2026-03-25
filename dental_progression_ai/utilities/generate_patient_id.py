from database.patient_manager import PatientManager

def generate_next_patient_id():
    """
    Generates a unique, sequential 4-5 digit patient ID.
    Starts at 1000 if no patients exist.
    """
    manager = PatientManager()
    last_id = manager.get_last_patient_id()
    
    if last_id is None:
        return 1000  # Starting ID
    
    try:
        return int(last_id) + 1
    except ValueError:
        # Fallback in case of corrupted data
        return 1000
