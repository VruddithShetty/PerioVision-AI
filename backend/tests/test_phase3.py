"""Security Lab, demo seeding and the synthetic demo pipeline."""
import numpy as np

from app.ml.measurement.bone_loss import bone_loss_for_tooth
from app.ml.preprocessing.clahe import apply_clahe
from app.ml.synthetic import make_radiograph
from app.services.analysis_service import demo_detections, demo_landmarks


def data(r):
    return r.get_json()["data"]


def test_security_lab_all_attacks_are_defended(client, auditor):
    listing = data(client.get("/api/security-lab", headers=auditor))
    # Not a fixed count: scenarios are added as controls are. What must hold is that
    # every scenario the lab offers is one it can actually run and defend.
    assert len(listing) >= 7
    r = client.post("/api/security-lab/run-all", headers=auditor)
    body = r.get_json()
    assert r.status_code == 200
    assert body["meta"]["total"] == len(listing)
    assert body["meta"]["defended"] == body["meta"]["total"]
    for scenario in body["data"]:
        assert scenario["defended"], scenario
        assert scenario["steps"] and all(s["passed"] for s in scenario["steps"])


def test_security_lab_single_run_and_permissions(client, auditor, dentist):
    r = client.post("/api/security-lab/audit-tamper/run", headers=auditor)
    assert data(r)["defended"]
    assert any("#4" in s["detail"] for s in data(r)["steps"])
    assert client.post("/api/security-lab/audit-tamper/run", headers=dentist).status_code == 403
    assert client.post("/api/security-lab/nope/run", headers=auditor).status_code == 404


def test_security_lab_does_not_touch_the_real_audit_chain(client, auditor):
    client.post("/api/security-lab/run-all", headers=auditor)
    assert data(client.get("/api/audit/verify", headers=auditor))["chain_intact"]


def test_demo_pipeline_recovers_planted_bone_loss():
    for planted in (8, 25, 40):
        gray = make_radiograph([planted] * 12)
        dets = demo_detections(apply_clahe(gray))
        assert len(dets) == 12
        measured = [bone_loss_for_tooth(demo_landmarks(gray, d))["bone_loss_pct"] for d in dets]
        assert abs(np.median(measured) - planted) < 3


def test_demo_seed_creates_a_complete_demo(client, dentist):
    from app.services.demo_seed import seed

    result = seed(force=True)
    assert result["seeded"] and len(result["patients"]) == 4 and result["analyses"] == 9
    assert result["report_id"]
    patients = data(client.get("/api/patients", headers=dentist))
    assert sum("(synthetic)" in p["patient_name"] for p in patients) >= 4
    patient_b = result["patients"][1]
    prog = data(client.get(f"/api/patients/{patient_b}/progression", headers=dentist))
    assert prog["summary"]["visits"] == 3
    raw_labels = {c["raw_label"] for c in prog["latest"]}
    assert raw_labels & {"progressing", "rapidly progressing"}
    queue = data(client.get("/api/review/queue", headers=dentist))
    assert queue  # demo cases always need review
    ok = data(client.get(f"/api/reports/verify/{result['report_id']}"))
    assert ok["valid"]
