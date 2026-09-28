# Project Structure

Updated in Phase 1 of the restructure (2026-09-28). Every move is listed in `docs/CHANGELOG_RESTRUCTURE.md`.

```text
Dental_progression/                 # repository root = project root
├── README.md  PROJECT_STRUCTURE.md  Makefile  run.ps1
├── .env.example  .gitignore  docker-compose.yml
├── backend/
│   ├── wsgi.py                     # entry point (python wsgi.py)
│   ├── requirements.txt  requirements-dev.txt  pyproject.toml  Dockerfile
│   ├── app/
│   │   ├── __init__.py             # create_app() factory
│   │   ├── config.py  extensions.py
│   │   ├── api/                    # auth patients radiographs analysis progression reports audit security health
│   │   ├── services/               # analysis_service progression_service progression_velocity report_service container
│   │   ├── ml/
│   │   │   ├── preprocessing/      # clahe.py alignment.py
│   │   │   ├── detection/          # yolo_detector.py (YOLOv8 + Grad-CAM agreement)
│   │   │   ├── landmarks/          # cej_abc_extractor.py (YOLOv8-pose)
│   │   │   ├── measurement/        # bone_loss.py
│   │   │   ├── explainability/     # overlay.py
│   │   │   ├── uncertainty/        # (Phase 2: conformal, review router)
│   │   │   └── fusion/             # multimodal_risk.py
│   │   ├── security/               # crypto model_signing audit_log audit_middleware rbac upload_guard
│   │   │                           # adversarial watermark honeypot incident_response secrets session ...
│   │   ├── models/                 # MongoDB managers: connection doctors patients xrays audit ...
│   │   ├── schemas/  utils/
│   ├── scripts/                    # training, dataset and maintenance tools
│   ├── weights/                    # model weights (gitignored)
│   ├── keys/                       # signing keys (private key gitignored)
│   ├── logs/  storage/             # runtime (gitignored)
│   ├── tests/                      # pytest
│   └── legacy/                     # old/duplicate code, not imported
├── frontend/                       # React app (Phase 4)
├── docs/                           # AUDIT_REPORT, CHANGELOG_RESTRUCTURE, security & TALPA docs, reference/
├── data/                           # gitignored; sample/ = synthetic only
├── notebooks/
└── tools/streamlit_prototype/      # old Streamlit UI, frozen snapshot
```
