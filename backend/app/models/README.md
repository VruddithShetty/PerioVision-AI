# app/models

MongoDB data layer (not ML models): `connection.py` (demo mode uses in-memory mongomock), `doctors.py` (user accounts + login sessions), `patients.py` (encrypted identity fields + clinical fields), `analyses.py` (analyses, review decisions, signed reports), `audit.py` (thin wrapper over the audit log).
