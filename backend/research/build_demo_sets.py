"""Build demonstration folders of radiographs that the app is known to handle well, each film checked end to end.

Three folders (default ~/Downloads/PerioVision_demo):
  1_periapical_training_films  DenPAR TRAINING films (the landmark model learned from these): the 100 it reads best
  2_periapical_unseen_films    DenPAR TEST films (never seen in training): the 100 it reads best
  3_panoramic_films            Aga Khan University OPGs from folders 1 and 3 (the detector was fine-tuned on these
                               folders): the 100 it numbers best

"Reads best" = lowest bone-loss error against the specialist reference (periapical) or highest tooth-level F1 with the
right FDI number (panoramic). Then EVERY selected film goes through the real API exactly as the web app sends it
(POST /api/radiographs, then POST /api/analyses) with the real signed models; a film that errors or yields no tooth is
replaced by the next candidate. Each folder gets README.txt (source, licence, how it was chosen) and
expected_results.csv (what the app returned), so the presenter knows in advance what each film shows.

These folders are for DEMONSTRATION. They are selected, so they are NOT an evaluation: the measured accuracy is in
docs/RESULTS_WITH_CI.md.

Usage (from backend/; CPU, about 1-2 hours):
    python -m research.build_demo_sets --out ~/Downloads/PerioVision_demo
"""
from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
import random
import shutil
import sys

os.environ.setdefault("DB_MODE", "demo")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))           # backend/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
LEAKED = {"166", "852", "1028", "158", "899"}


# ------------------------------------------------------------------ candidate scoring
def score_periapical(images: str, labels: str, limit: int, seed: int) -> list[tuple[float, str]]:
    """[(mean bone-loss error, image path)] for films where every labelled tooth was found and measured."""
    from evaluate_landmarks import read_labels

    from app.ml.landmarks.cej_abc_extractor import _iou
    from app.ml.measurement.bone_loss import bone_loss_for_tooth
    from app.services.analysis_service import locate_teeth, measured

    files = sorted(glob.glob(os.path.join(images, "*.jpg")))
    files = [f for f in files if os.path.splitext(os.path.basename(f))[0] not in LEAKED]
    random.Random(seed).shuffle(files)  # audit-ok: seeded choice of demo candidates
    out = []
    for n, f in enumerate(files[:limit], 1):
        g = cv2.imread(f, cv2.IMREAD_GRAYSCALE)
        g = g.reshape(g.shape[:2])
        lab = os.path.join(labels, os.path.basename(f).replace(".jpg", ".txt"))
        if not os.path.exists(lab):
            continue
        truth = read_labels(lab, g.shape[1], g.shape[0])
        res = locate_teeth(g)
        if res["image_type"] != "periapical" or not truth:
            continue
        errs, used, complete = [], set(), True
        for ref in truth:
            best = max(((i, _iou(d["bbox"], ref["bbox"])) for i, d in enumerate(res["detections"]) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            lm = res["landmarks"].get(res["detections"][best[0]]["tooth_id"]) if best[0] is not None else None
            if best[0] is None or best[1] < 0.5 or not measured(lm):
                complete = False
                break
            used.add(best[0])
            errs.append(abs(bone_loss_for_tooth(lm)["bone_loss_pct"] - bone_loss_for_tooth(ref)["bone_loss_pct"]))
        if complete:
            out.append((float(np.mean(errs)), f))
        if n % 25 == 0:
            print(f"  scored {n}/{min(limit, len(files))} periapical candidates", flush=True)
    return sorted(out)


def score_unseen_from_evidence(images: str) -> list[tuple[float, str]]:
    """Unseen test films ranked by the stored app-path evaluation (docs/evidence/predictions/denpar_test_per_tooth.csv)."""
    rows = list(csv.DictReader(open(os.path.join(ROOT, "docs", "evidence", "predictions", "denpar_test_per_tooth.csv"),
                                    encoding="utf-8")))
    films = {}
    for r in rows:
        films.setdefault(r["image"], []).append(r)
    out = []
    for f, rs in films.items():
        if os.path.splitext(f)[0] in LEAKED or any(r["status"] != "measured" for r in rs):
            continue
        out.append((float(np.mean([abs(float(r["pred_pct"]) - float(r["ref_pct"])) for r in rs])), os.path.join(images, f)))
    return sorted(out)


def score_panoramic(aku_root: str) -> list[tuple[float, str]]:
    """[(-F1 with right FDI number, image path)] for AKU folders 1 and 3."""
    from evaluate_detector_external import ground_truth

    from app.ml.landmarks.cej_abc_extractor import _iou
    from app.services import container

    det = container.tooth_detector()
    out = []
    anns = sorted(glob.glob(os.path.join(aku_root, "folder 1", "annotations", "*.json")) +
                  glob.glob(os.path.join(aku_root, "folder 3", "annotations", "*.json")))
    for n, ann in enumerate(anns, 1):
        stem = os.path.splitext(os.path.basename(ann))[0]
        imgs = glob.glob(os.path.join(os.path.dirname(ann), "..", "OPGs", stem + ".*"))
        img = cv2.imread(imgs[0]) if imgs else None
        if img is None:
            continue
        gt, pred, used, tp, right = ground_truth(ann), det.detect_teeth(img), set(), 0, 0
        for g in gt:
            best = max(((i, _iou(g["bbox"], p["bbox"])) for i, p in enumerate(pred) if i not in used),
                       key=lambda x: x[1], default=(None, 0.0))
            if best[0] is not None and best[1] >= 0.5:
                used.add(best[0])
                tp += 1
                right += pred[best[0]]["tooth_id"] == g["fdi"]
        fp, fn = len(pred) - len(used), len(gt) - tp
        f1 = 2 * right / max(1, 2 * right + 2 * (tp - right) + fp + fn)
        out.append((-f1, os.path.abspath(imgs[0])))
        if n % 25 == 0:
            print(f"  scored {n}/{len(anns)} panoramic candidates", flush=True)
    return sorted(out)


# ------------------------------------------------------------------ end-to-end API check
class ApiCheck:
    """The real app (Flask test client) with the real signed models and the demo login from .env."""

    def __init__(self):
        from app import create_app

        os.environ.setdefault("SEED_DEMO_DATA", "0")
        self.app = create_app()
        self.client = self.app.test_client()
        self.last_reason = None
        self._login()

    def _login(self):
        """Access tokens live 15 minutes (security setting); log in again whenever one has expired."""
        email, password = os.getenv("DEMO_EMAIL"), os.getenv("DEMO_PASSWORD")
        if not email or not password:
            raise SystemExit("DEMO_EMAIL / DEMO_PASSWORD are not set in .env")
        ua = {"User-Agent": "periovision-demo-check/1.0"}
        r = self.client.post("/api/auth/login", json={"email": email, "password": password}, headers=ua)
        if r.status_code != 200:
            raise SystemExit(f"demo login failed ({r.status_code})")
        self.h = {"Authorization": f"Bearer {r.get_json()['data']['access_token']}", **ua}

    def _call(self, method, url, **kw):
        import time

        image = kw["data"]["image"] if isinstance(kw.get("data"), dict) and "image" in kw["data"] else None
        for _ in range(10):                      # the app's rate limits (e.g. 10 analyses a minute) apply here too
            if image is not None:
                image[0].seek(0)
            r = getattr(self.client, method)(url, headers=self.h, **kw)
            if r.status_code != 429:
                break
            time.sleep(int(r.headers.get("Retry-After") or 15) + 1)
        if r.status_code == 401:
            self._login()
            if "data" in kw and isinstance(kw["data"], dict) and "image" in kw["data"]:
                name, buf = kw["data"]["image"][1], kw["data"]["image"][0]
                buf.seek(0)
                kw["data"] = {"image": (buf, name)}
            r = getattr(self.client, method)(url, headers=self.h, **kw)
        return r

    def _fail(self, why: str):
        self.last_reason = why
        return None

    def analyse(self, path: str, expect: str) -> dict | None:
        """None if the app fails on this film (reason in self.last_reason); otherwise what it returned."""
        r = self._call("post", "/api/patients", json={
            "name": "Demo Check", "age": 45, "sex": "female", "smoking_status": "never", "diabetic": False})
        if r.status_code != 201:
            return self._fail(f"patient create {r.status_code}")
        pid = r.get_json()["data"]["patient_id"]
        with open(path, "rb") as fh:
            up = self._call("post", "/api/radiographs", content_type="multipart/form-data",
                            data={"image": (io.BytesIO(fh.read()), os.path.basename(path))})
        if up.status_code != 201:
            return self._fail(f"upload {up.status_code}: {(up.get_json() or {}).get('error')}")
        a = self._call("post", "/api/analyses", json={"upload_id": up.get_json()["data"]["upload_id"], "patient_id": pid})
        if a.status_code != 201:
            return self._fail(f"analysis {a.status_code}: {(a.get_json() or {}).get('error')}")
        d = a.get_json()["data"]
        if d.get("mode") != "live" or not d.get("teeth"):
            return self._fail("no live result or no teeth")
        if d.get("image_type") != expect:
            return self._fail(f"read as {d.get('image_type')} film, expected {expect}")
        measured = [t for t in d["teeth"] if t.get("bone_loss_pct") is not None]
        worst = max(measured, key=lambda t: t["bone_loss_pct"]) if measured else None
        pano = d.get("panoramic_assessment") or {}
        wt = pano.get("worst_tooth") if isinstance(pano, dict) else None
        if d.get("image_type") == "periapical" and not measured:
            return self._fail("no tooth measured")                # a periapical demo film must show bone loss
        if d.get("image_type") == "panoramic" and not wt:
            return self._fail("no whole-film estimate")           # a panoramic demo film must show the estimate
        return {"image_type": d.get("image_type"), "teeth_found": len(d["teeth"]), "teeth_measured": len(measured),
                "worst_tooth": worst["tooth_id"] if worst else "",
                "worst_bone_loss_pct": worst["bone_loss_pct"] if worst else "",
                "worst_stage": worst.get("stage") if worst else "",
                "panoramic_worst_tooth_pct": wt.get("bone_loss_pct") if wt else "",
                "panoramic_stage": wt.get("stage") if wt else "",
                "review": (d.get("review") or {}).get("status", "")}


README = {
    "1_periapical_training_films": (
        "DenPAR periapical radiographs from the TRAINING split (the landmark model learned from these films).\n"
        "Chosen: the 100 films, out of a seeded random sample of training films, on which the app's bone-loss reading "
        "is closest to the specialist reference, every tooth found and measured.\n"
        "Use for: the most reliable live demonstration. If asked: yes, the model was trained on these films."),
    "2_periapical_unseen_films": (
        "DenPAR periapical radiographs from the TEST split (never used for training or tuning; the 5 films duplicated "
        "across DenPAR splits are excluded).\n"
        "Chosen: the 100 test films the app reads closest to the specialist reference (from the stored test-set "
        "evaluation), every tooth found and measured.\n"
        "Use for: showing the app on films it has never seen. If asked: these are unseen films, selected as the ones "
        "it reads best, so they show the app at its best, not its average (average: docs/RESULTS_WITH_CI.md)."),
    "3_panoramic_films": (
        "Aga Khan University panoramic radiographs (OPGs) from folders 1 and 3 (the tooth detector was fine-tuned on "
        "these folders).\n"
        "Chosen: the 100 films with the highest share of teeth found with the right FDI number.\n"
        "Use for: tooth detection and numbering, and the whole-film (patient-level) bone-loss estimate. Per-tooth "
        "bone-loss numbers are not shown on panoramic films by design."),
}
LICENCE = {
    "1_periapical_training_films": "DenPAR (Zenodo 10.5281/zenodo.16645076), CC BY 4.0. Credit the DenPAR authors.",
    "2_periapical_unseen_films": "DenPAR (Zenodo 10.5281/zenodo.16645076), CC BY 4.0. Credit the DenPAR authors.",
    "3_panoramic_films": "Aga Khan University OPG dataset (Zenodo 10.5281/zenodo.10538750), CC BY 4.0. Credit the authors.",
}


def reference_worst(path: str, labels_root: str) -> dict:
    """The specialist reference for a DenPAR film: its worst tooth's bone loss % and stage (from the labels)."""
    from evaluate_landmarks import read_labels

    from app.ml.measurement.bone_loss import bone_loss_for_tooth
    from app.ml.measurement.staging import stage_for_pct

    split = os.path.basename(os.path.dirname(path))
    lab = os.path.join(labels_root, "labels", split, os.path.basename(path).replace(".jpg", ".txt"))
    g = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    vals = [bone_loss_for_tooth(t)["bone_loss_pct"] for t in read_labels(lab, g.shape[1], g.shape[0])]
    vals = [v for v in vals if v is not None]
    if not vals:
        return {"specialist_worst_bone_loss_pct": "", "specialist_worst_stage": ""}
    return {"specialist_worst_bone_loss_pct": round(max(vals), 2), "specialist_worst_stage": stage_for_pct(max(vals))}


def fill(name: str, candidates: list[tuple[float, str]], out_dir: str, n: int, api: ApiCheck,
         labels_root: str | None = None) -> dict:
    dest = os.path.join(out_dir, name)
    os.makedirs(dest, exist_ok=True)
    rows, rejected, reasons = [], 0, []
    for score, path in candidates:
        if len(rows) >= n:
            break
        res = api.analyse(path, "panoramic" if name.startswith("3_") else "periapical")
        if res is None:
            rejected += 1
            reasons.append({"file": os.path.basename(path), "reason": api.last_reason})
            continue
        shutil.copy2(path, os.path.join(dest, os.path.basename(path)))
        ref = reference_worst(path, labels_root) if labels_root and not name.startswith("3_") else {}
        rows.append({"file": os.path.basename(path),
                     "selection_score": round(-score if name.startswith("3_") else score, 4), **res, **ref})
        if len(rows) % 10 == 0:
            print(f"  {name}: {len(rows)}/{n} checked and copied ({rejected} rejected)", flush=True)
    if reasons:
        json.dump(reasons, open(os.path.join(dest, "rejected_films.json"), "w", encoding="utf-8"), indent=1)
    if not rows:
        raise SystemExit(f"{name}: no film passed the check; see rejected_films.json")
    with open(os.path.join(dest, "expected_results.csv"), "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    metric = ("tooth-level F1 with the right FDI number" if name.startswith("3_")
              else "mean bone-loss error against the specialist (points)")
    open(os.path.join(dest, "README.txt"), "w", encoding="utf-8").write(
        f"{README[name]}\n\nLicence: {LICENCE[name]}\n\nexpected_results.csv: what the app returned for each film in "
        f"the end-to-end check (selection_score = {metric}). Every film here was uploaded and analysed through the "
        "app's API with the signed models without an error. Selected films: a demonstration set, not an evaluation.\n"
        + ("specialist_worst_*: the DenPAR specialist reference for the film's worst tooth, to compare with the app's "
           "worst_* columns during the demo.\n" if not name.startswith("3_") else "")
        + "review = review_required is expected: the app asks a dentist to sign off every case before a report.\n")
    return {"folder": name, "films": len(rows), "rejected_by_api_check": rejected}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="~/Downloads/PerioVision_demo")
    ap.add_argument("--denpar-labels", default="~/Downloads/DenPAR/pose_dataset_fixed")
    ap.add_argument("--aku", default="~/Downloads/OPG-AKU/Niihhaa-Dataset-4ac91db/dataset")
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--train-candidates", type=int, default=170)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    out = os.path.expanduser(args.out)
    labels = os.path.expanduser(args.denpar_labels)
    os.makedirs(out, exist_ok=True)
    cache = os.path.join(out, "candidates_cache.json")
    sets = json.load(open(cache, encoding="utf-8")) if os.path.exists(cache) else None
    if sets is None:
        print("scoring candidates ...", flush=True)
        sets = {
        "1_periapical_training_films": score_periapical(os.path.join(labels, "images", "train"),
                                                        os.path.join(labels, "labels", "train"),
                                                        args.train_candidates, args.seed),
        "2_periapical_unseen_films": score_unseen_from_evidence(os.path.join(labels, "images", "test")),
        "3_panoramic_films": score_panoramic(os.path.expanduser(args.aku)),
        }
        json.dump(sets, open(cache, "w", encoding="utf-8"))
    print({k: len(v) for k, v in sets.items()}, "candidates", flush=True)
    api = ApiCheck()
    summary = [fill(name, cands, out, args.n, api, labels) for name, cands in sets.items()]
    open(os.path.join(out, "README.txt"), "w", encoding="utf-8").write(
        "PerioVision AI demonstration films\n\n"
        "Three folders of radiographs the app handles well, each film checked end to end through the app's API with "
        "the signed models (no errors). See README.txt in each folder for the source, licence and how the films were "
        "chosen; expected_results.csv lists what the app returned for every film.\n\n"
        "These are SELECTED films for live demonstration. The app's measured accuracy, on all unseen test films with "
        "95 % confidence intervals, is in docs/RESULTS_WITH_CI.md of the project.\n\n" + json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
