"""Regression guards: no synthetic or defaulted number may reach a user as if it were a result.

1. Records written by the demo seeder carry source = "synthetic_demo" and mode = "demo";
   records from the upload API never do.
2. A static scan fails the build if code that shapes results reintroduces the patterns this
   audit removed (fallback numbers for unmeasured values, random numbers, typed-in metrics).
"""
import io
import re
from pathlib import Path

from app.services import container, demo_seed
from tests.conftest import synthetic_radiograph

ROOT = Path(__file__).resolve().parents[2]


def data(r):
    return r.get_json()["data"]


def test_seeded_records_are_tagged_synthetic_and_uploads_are_not(client, dentist):
    demo_seed.seed(force=True)
    seeded = list(container.analysis_store().collection.find({"source": demo_seed.SYNTHETIC}, {"_id": 0}))
    assert seeded and all(a["mode"] == "demo" for a in seeded)
    charts = list(container.chart_store().collection.find({"notes": "Synthetic demo chart"}, {"_id": 0}))
    assert charts and all(c.get("source") == demo_seed.SYNTHETIC for c in charts)

    pid = data(client.post("/api/patients", headers=dentist, json={"name": "Upload Patient", "age": 44,
                                                                   "smoking_status": "never"}))["patient_id"]
    up = data(client.post("/api/radiographs", headers=dentist, content_type="multipart/form-data",
                          data={"image": (io.BytesIO(synthetic_radiograph(seed=9)), "scan.png")}))
    body = client.post("/api/analyses", headers=dentist,
                       json={"upload_id": up["upload_id"], "patient_id": pid, "visit_date": "2026-05-01"}).get_json()
    assert body["data"]["source"] == "uploaded_radiograph"
    assert body["mode"] == "demo"          # API envelope says demo mode (in-memory DB, test run)
    for a in container.analysis_store().collection.find({"mode": "live"}, {"_id": 0}):
        assert a.get("source") != demo_seed.SYNTHETIC, a["analysis_id"]


def test_demo_teeth_without_a_crest_are_not_measured():
    import numpy as np

    from app.services.analysis_service import demo_landmarks, measured

    flat = np.full((700, 1400), 60, np.uint8)               # no bone anywhere: the crest cannot be found
    lm = demo_landmarks(flat, {"bbox": [100.0, 150.0, 170.0, 560.0]})
    assert not measured(lm)


# (path glob, forbidden regex, why) -- lines may opt out with the marker "audit-ok: <reason>"
FORBIDDEN = [
    ("frontend/src/pages/**/*.tsx", r"bone_loss_pct\s*\?\?\s*0", "unmeasured bone loss shown as 0 %"),
    ("frontend/src/components/**/*.tsx", r"bone_loss_pct\s*\?\?\s*0", "unmeasured bone loss shown as 0 %"),
    ("frontend/src/**/*.tsx", r"probability\s*\?\?\s*\d", "missing risk shown as a default score"),
    ("frontend/src/pages/**/*.tsx", r"DEFAULT_RATE|hba1c\s*\?\?\s*\(", "typed-in clinical rates or lab values"),
    ("frontend/src/pages/**/*.tsx", r"Math\.random", "random numbers in a results page"),
    ("frontend/src/components/**/*.tsx", r"Math\.random", "random numbers in a results component"),
    ("frontend/src/pages/about/*.tsx", r"\d+(\.\d+)?\s*%\s*(precision|recall|mAP|coverage|stage agreement)",
     "accuracy typed into the page instead of read from /api/models/metrics"),
    ("backend/app/**/*.py", r"bone_loss_pct\S*\s+or\s+0", "unmeasured bone loss treated as 0"),
    ("backend/app/ml/**/*.py", r"\b(random\.|np\.random\.(rand|randn|randint|normal|uniform)\()", "random values in the ML path"),
    ("backend/app/services/analysis_service.py", r"heuristic_landmarks\(det\[\"bbox\"\]\)\)", "geometric fallback used as a measurement"),
]


def test_static_scan_for_fake_number_patterns():
    hits = []
    for pattern, regex, why in FORBIDDEN:
        rx = re.compile(regex)
        for path in ROOT.glob(pattern):
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if rx.search(line) and "audit-ok:" not in line:
                    hits.append(f"{path.relative_to(ROOT)}:{n}: {why}: {line.strip()[:120]}")
    assert not hits, "\n".join(hits)
