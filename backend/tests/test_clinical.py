"""Chairside clinical tools: perio chart indices, concordance, prognosis, recall, care plan API."""
from app.services.clinical_service import (
    concordance,
    recall_interval,
    summarize_chart,
    tooth_prognosis,
)


def data(r):
    return r.get_json()["data"]


CHART = {
    "teeth": {
        "16": {"pd": [6, 3, 5, 4, 3, 6], "rec": [1, 0, 1, 0, 0, 1], "bop": [True, False, True, True, False, True],
               "plaque": [True] * 6, "mobility": 1, "furcation": 2},
        "11": {"pd": [2, 2, 2, 2, 1, 2], "rec": [0] * 6, "bop": [False] * 6, "plaque": [False] * 6},
        "46": {"missing": True},
    }
}


def test_chart_indices():
    s = summarize_chart(CHART)
    assert s["teeth_present"] == 2 and s["teeth_missing"] == 1
    t16 = s["teeth"]["16"]
    assert t16["cal"] == [7, 3, 6, 4, 3, 7] and t16["interdental_cal"] == 7
    assert t16["clinical_stage"] == "III" and s["teeth"]["11"]["clinical_stage"] == "I"
    assert s["bop_pct"] == round(100 * 4 / 12, 1)
    assert s["sites_pd_4_plus"] == 4 and s["sites_pd_6_plus"] == 2
    assert s["clinical_stage"] == "III"
    assert s["gingival_status"] == "periodontitis with active inflammation"


def test_concordance_flags_disagreement():
    s = summarize_chart(CHART)
    analysis = {"teeth": [
        {"tooth_id": "16", "tooth_id_source": "model_fdi_class", "stage": "I", "bone_loss_pct": 10},
        {"tooth_id": "11", "tooth_id_source": "model_fdi_class", "stage": "I", "bone_loss_pct": 8},
        {"tooth_id": "T1", "tooth_id_source": "positional_estimate", "stage": "III", "bone_loss_pct": 40},
    ]}
    rows = {r["tooth_id"]: r for r in concordance(s, analysis)}
    assert rows["16"]["status"] == "clinical worse" and "angular" in rows["16"]["hint"]
    assert rows["11"]["status"] == "agree"
    assert "T1" not in rows  # teeth without a reliable number are never compared


def test_prognosis_categories():
    assert tooth_prognosis(10)["category"] == "favourable"
    assert tooth_prognosis(30)["category"] == "questionable"
    assert tooth_prognosis(20, furcation=3)["category"] == "unfavourable"
    assert tooth_prognosis(80)["category"] == "hopeless"
    assert tooth_prognosis(20, mobility=3)["category"] == "hopeless"


def test_recall_interval():
    assert recall_interval("C", "low", 5, False)["months"] == 3
    assert recall_interval("A", "low", 35, False)["months"] == 3
    assert recall_interval("B", "low", 5, False)["months"] == 4
    assert recall_interval("A", "low", 5, False)["months"] == 6
    assert recall_interval("A", "low", 5, True)["months"] == 3


def test_chart_api_and_care_plan(client, dentist, technician, auditor):
    pid = data(client.post("/api/patients", headers=dentist, json={
        "name": "Chart Patient", "age": 50, "smoking_status": "current", "cigarettes_per_day": 12}))["patient_id"]
    body = {"exam_date": "2026-09-01", "teeth": {k: v for k, v in CHART["teeth"].items()}}
    # the technician is not on this patient's care team yet
    assert client.post(f"/api/patients/{pid}/perio-charts", headers=technician, json=body).status_code == 404
    r = client.post(f"/api/patients/{pid}/perio-charts", headers=dentist, json=body)
    assert r.status_code == 201, r.get_json()
    assert data(r)["summary"]["clinical_stage"] == "III"
    assert client.get(f"/api/patients/{pid}/perio-charts", headers=auditor).status_code == 403

    bad = {"exam_date": "2026-09-01", "teeth": {"99": {"pd": [1] * 6}}}
    assert client.post(f"/api/patients/{pid}/perio-charts", headers=dentist, json=bad).status_code == 422
    bad = {"exam_date": "2026-09-01", "teeth": {"16": {"pd": [30] * 6}}}
    assert client.post(f"/api/patients/{pid}/perio-charts", headers=dentist, json=bad).status_code == 422

    plan = data(client.get(f"/api/patients/{pid}/care-plan", headers=dentist))
    assert plan["stage"] == "III" and plan["clinical_stage"] == "III"
    assert plan["recall"]["months"] == 3                     # BOP ≥ 30 %
    assert plan["next_recall_due"] == "2026-12-01"
    assert plan["referral_suggested"]
    step1 = plan["steps"][0]["items"]
    assert any("Smoking cessation" in i for i in step1)
    assert plan["steps"][2]["indicated"]                     # stage III -> step 3


def test_recall_board(client, dentist):
    rows = client.get("/api/recall", headers=dentist)
    assert rows.status_code == 200
    body = rows.get_json()
    assert {"overdue", "due_soon"} <= set(body["meta"])
    for r in body["data"]:
        assert r["status"] in ("overdue", "due soon", "scheduled")
