# backend

The PerioVision AI REST API: Flask + MongoDB + PyTorch/YOLOv8 + OpenCV.

```
backend/
├── wsgi.py            # entry point: python wsgi.py  (or any WSGI server: wsgi:app)
├── app/               # the application package (see app/README.md)
├── scripts/           # training, dataset and maintenance tools
├── weights/           # model weight files (gitignored)
├── keys/              # model/report signing keys (private key gitignored)
├── tests/             # pytest suite
├── legacy/            # old/duplicate code kept for reference, not imported
├── requirements.txt   # pinned runtime dependencies
└── requirements-dev.txt
```

Run it (from the repository root, after copying `.env.example` to `.env`):

```bash
cd backend
python -m pip install -r requirements-dev.txt
python wsgi.py
```

The API listens on http://127.0.0.1:5000 and `GET /api/health` reports whether it is in `demo` or `live` mode.
Demo credentials, if any, come from `DEMO_EMAIL` / `DEMO_PASSWORD` in `.env` and are for demos only.
