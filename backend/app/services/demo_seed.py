"""Seed synthetic demo data so the whole app can be shown without GPUs or real patients.

Creates clearly labelled SYNTHETIC patients with different clinical profiles,
two or three visits each (synthetic radiographs whose bone levels change over
time), runs the normal analysis pipeline on them in demo mode, signs off some
cases as a dentist would, and issues one signed report. Idempotent: a marker
in the database stops it from seeding twice.
"""
from __future__ import annotations

import datetime as dt
import logging
import os

from app.ml import synthetic
from app.models.connection import db
from app.services import container

logger = logging.getLogger(__name__)
MARKER = {"_id": "demo_seed_v1"}
SYNTHETIC = "synthetic_demo"   # every seeded record carries source = SYNTHETIC; live records never do

PATIENTS = [
    # name, clinical profile, bone loss per visit (12 teeth each visit, % below CEJ)
    ("Demo Patient A (synthetic)", {"age": 34, "sex": "female", "smoking_status": "never", "diabetic": False,
                                    "hba1c": 5.2}, [[6] * 12, [6.5] * 12]),
    ("Demo Patient B (synthetic)", {"age": 52, "sex": "male", "smoking_status": "current", "cigarettes_per_day": 15,
                                    "diabetic": False, "hba1c": 5.6},
     [[12, 14, 18, 20, 16, 12, 10, 12, 15, 18, 20, 14], [16, 19, 24, 27, 20, 14, 11, 14, 19, 24, 27, 18],
      [20, 24, 31, 35, 25, 16, 12, 16, 24, 31, 36, 22]]),
    ("Demo Patient C (synthetic)", {"age": 61, "sex": "female", "smoking_status": "former", "diabetic": True,
                                    "hba1c": 7.8, "teeth_lost_perio": 2},
     [[30, 32, 36, 40, 38, 34, 30, 33, 36, 40, 42, 35], [33, 35, 40, 44, 41, 36, 31, 35, 39, 44, 46, 38]]),
    ("Demo Patient D (synthetic)", {"age": 45, "sex": "male", "smoking_status": "never", "diabetic": True,
                                    "hba1c": 6.6}, [[18] * 12, [15] * 12]),
]


def already_seeded() -> bool:
    return db["meta"].find_one(MARKER) is not None


def seed(force: bool = False) -> dict:
    if already_seeded() and not force:
        return {"seeded": False, "reason": "already seeded"}
    users = container.doctor_manager()
    owner = None
    for env in ("DEMO_EMAIL", "DEMO_ADMIN_EMAIL"):
        email = os.getenv(env)
        if email:
            owner = users.collection.find_one({"email": email.strip().lower()})
            if owner:
                break
    if owner is None:
        return {"seeded": False, "reason": "no demo account configured (set DEMO_EMAIL / DEMO_PASSWORD in .env)"}
    user = {"id": owner["doctor_id"], "role": "dentist", "name": owner.get("name", "Demo Dentist")}

    from app.services.analysis_service import run_analysis

    patients_mgr, analyses = container.patient_manager(), container.analysis_store()
    today = dt.date.today()
    created, analysis_ids = [], []
    for p_index, (name, clinical, visits) in enumerate(PATIENTS):
        patient = patients_mgr.create_patient({"name": name, "notes": "SYNTHETIC DEMO RECORD - not a real person",
                                               **clinical}, owner_id=user["id"])
        raw = patients_mgr.get_raw(patient["patient_id"])
        created.append(patient["patient_id"])
        for v_index, levels in enumerate(visits):
            years_back = len(visits) - 1 - v_index
            # Stagger last visits so the recall board shows overdue, due-soon and scheduled patients.
            offset = {0: 160, 1: 20, 2: 40, 3: 250}.get(p_index, 20 * p_index)
            visit_date = (today - dt.timedelta(days=365 * years_back + offset)).isoformat()
            png = synthetic.to_png(synthetic.make_radiograph(levels, seed=p_index * 10 + v_index))
            record = run_analysis(png, raw, user, visit_date=visit_date, force_demo=True,
                                  upload_meta={"kind": "png", "source": "synthetic demo"}, source=SYNTHETIC)
            analysis_ids.append(record["analysis_id"])

    # A dentist signs off the latest visit of the first two patients; one gets a correction.
    latest = [analyses.latest_for_patient(pid) for pid in created]
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    for i, a in enumerate(latest[:2]):
        corrections = [] if i == 0 else [{"tooth_id": a["teeth"][0]["tooth_id"], "bone_loss_pct": 22.0, "stage": "II",
                                          "note": "Demo correction"}]
        analyses.record_review(a["analysis_id"], {
            "status": "approved" if i == 0 else "corrected", "reviewer_id": user["id"],
            "reviewer_name": user["name"], "reviewer_role": "dentist", "at": now,
            "comment": "Synthetic demo sign-off", "corrections": corrections})

    # Chairside perio charts for the latest visit, derived from the planted bone levels.
    # Patient B gets two deliberately discordant teeth so the concordance check has something to show.
    import random

    charts = container.chart_store()
    rnd = random.Random(42)
    for pid, a in zip(created, latest):
        teeth = {}
        for t in a["teeth"]:
            bl = t.get("bone_loss_pct")
            if bl is None:                                 # not measured: no synthetic chart values derived from it
                continue
            cal = max(1, round(bl * 0.13 + 1))            # ~13 mm root: % -> mm, plus 1 mm biological width
            if pid == created[1] and t["tooth_id"] in ("44", "34"):
                cal += 4                                   # angular defect the X-ray under-reads
            rec = [rnd.choice([0, 0, 1]) for _ in range(6)]
            pd = [max(1, min(12, cal - r + rnd.choice([-1, 0, 0, 1]))) for r in rec]
            bop = [p >= 4 and rnd.random() < 0.7 for p in pd]
            teeth[t["tooth_id"]] = {"pd": pd, "rec": rec, "bop": bop, "plaque": [rnd.random() < 0.3 for _ in pd],
                                    "mobility": 1 if bl > 35 else 0, "furcation": 1 if bl > 30 and t["tooth_id"][1] in "67" else 0,
                                    "missing": False}
        charts.create({"patient_id": pid, "pseudo_id": a["pseudo_id"], "exam_date": a["visit_date"], "teeth": teeth,
                       "notes": "Synthetic demo chart", "source": SYNTHETIC, "examiner_id": user["id"], "examiner_name": user["name"]})

    report_id = None
    try:
        from app.services.report_service import create_report

        report_id = create_report(latest[0]["analysis_id"], user)["report_id"]
    except Exception as exc:  # signing key not configured: the rest of the demo still works
        logger.warning("Demo report not generated: %s", exc)

    db["meta"].replace_one(MARKER, {**MARKER, "at": now, "patients": created}, upsert=True)
    logger.info("Demo data seeded: %d patients, %d analyses", len(created), len(analysis_ids))
    return {"seeded": True, "patients": created, "analyses": len(analysis_ids), "report_id": report_id}
