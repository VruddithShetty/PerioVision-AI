# Architecture

```
                         ┌──────────────────────────── Browser ─────────────────────────────┐
                         │ React 18 + Vite (frontend/)                                      │
                         │  access token in memory · refresh token = httpOnly cookie         │
                         └───────────────┬──────────────────────────────────────────────────┘
                                         │ HTTPS in production (TLS proxy) · /api proxied in dev
                                         ▼
┌──────────────────────────────────── Flask backend (backend/app) ─────────────────────────────────────┐
│  security headers · CORS allow-list · rate limiter                                                   │
│  Zero Trust guard (every request): token → session → device → account → RBAC permission; else deny  │
│                                                                                                      │
│  api/  (thin routes, pydantic validation, envelope {data, meta, error, mode})                         │
│    auth  patients  radiographs  analysis  progression  clinical  reports  audit  security  health    │
│        │                  │                    │                      │                               │
│        ▼                  ▼                    ▼                      ▼                               │
│  services/            services/analysis   services/progression   services/report  services/clinical  │
│                             │                                         │                               │
│                             ▼                                         ▼                               │
│  ml/ quality gate → CLAHE → YOLOv8 FDI teeth → CEJ/crest/apex → bone loss & staging                  │
│      → Grad-CAM + ROI check → conformal interval → OOD/adversarial → review router → risk fusion      │
│      registry.py verifies the RSA-PSS signed manifest BEFORE any weight file is loaded               │
│                                                                                                      │
│  security/ crypto (AES-256-GCM, key ring) · model_signing (RSA-PSS) · audit_log (hash chain + Merkle) │
│            upload_guard · adversarial · honeypot · auth (bcrypt, JWT, TOTP) · rbac · zero_trust       │
└───────────────┬───────────────────────────────┬───────────────────────────────┬─────────────────────┘
                ▼                               ▼                               ▼
     MongoDB (or mongomock in demo)    Encrypted blob store             Audit anchors (outside the DB)
     users · sessions · patients*      storage/blobs/*.bin              logs/merkle_anchors.jsonl
     analyses · reports · charts       radiographs, overlays, PDFs      HMAC-authenticated Merkle roots
     audit_logs (hash chain)           AES-256-GCM, purpose-bound AAD
     * names/contacts/notes encrypted, blind-indexed; logs use pseudonyms (P-…)
```

## Request lifecycle (analysis)

1. **Upload** `POST /api/radiographs`: the upload guard checks size, extension, magic bytes and pixel dimensions, re-encodes the image (dropping EXIF), strips DICOM patient tags, runs a quality preview, and stores the clean PNG encrypted under a random ID.
2. **Analyse** `POST /api/analyses`: the service decrypts the upload, applies the quality gate (reject or warn), CLAHE, loads the signed detector and keypoint models from the registry (or labels the run as demo), finds teeth with FDI numbers, locates CEJ, crest and apex, computes bone loss and stage, builds a Grad-CAM heatmap, checks attention inside the periodontal band, attaches a conformal interval and stage set, screens for adversarial or out-of-distribution input, registers the image against the previous visit, compares teeth across visits, suggests a grade, fuses clinical and image features into a risk score, and routes the case to mandatory review when anything is uncertain.
3. **Store**: images (radiograph, annotated, Grad-CAM layer) go to the encrypted blob store; the analysis record keeps only blob IDs; an audit entry `PREDICTION` is written with the patient's pseudonym.
4. **Review** `POST /api/review/{id}`: a dentist approves, corrects or rejects; corrections are stored for retraining.
5. **Report** `POST /api/reports`: allowed only after sign-off; the PDF is built, its SHA-256 signed with RSA-PSS, stored encrypted; the QR code links to public verification.

## Trust boundaries

| Boundary | Control |
|---|---|
| Internet → API | TLS (proxy), CORS allow-list, rate limits, security headers |
| Request → handler | Zero Trust guard; unclassified routes denied |
| Handler → data | object-level patient checks (owner / care team), strict schemas (no Mongo operators) |
| Weights → inference | signed manifest verified before load |
| Data at rest | AES-256-GCM with key IDs; audit chain + external anchors |
| Result → patient care | conformal uncertainty, review router, dentist sign-off, signed reports |

## Frontend structure

`app/` (router), `pages/` (one folder per page), `components/` (`ui/` design system, `layout/`, `charts/`, `dental/`), `three/` (lazy 3D scenes with static fallback), `api/` (typed client + hooks), `store/` (auth state), `hooks/`, `lib/`, `styles/`.

## Modes

- **demo** (`DB_MODE=demo`): in-memory database, synthetic data seeded at start, encrypted demo files wiped at each start, a visible banner in the UI and `"mode": "demo"` in every response.
- **live** (`DB_MODE=production`): MongoDB, secrets required from `.env` (the app refuses to start without them).
