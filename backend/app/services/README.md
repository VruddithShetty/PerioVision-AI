# app/services

Business logic: `analysis_service.py` (the full pipeline, from quality gate to review routing), `progression_service.py` (tooth matching across visits, velocity, labels, reliability), `report_service.py` (signed PDF + verification), `storage_service.py` (encrypted blob storage), `container.py` (lazily created stores and models).
