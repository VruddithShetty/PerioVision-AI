"""Sample sizes and 95 % confidence intervals for every headline metric, plus staging confusion matrices.

Reads the per-item prediction files in docs/evidence/predictions/ (written by scripts/evaluate_landmarks.py,
scripts/evaluate_detector_external.py and research.export_predictions) and the summary metric files.
Every number is labelled with how it was obtained:

  VERIFIED     recomputed here from per-item predictions of the deployed model
  FROM-COUNTS  exact counts recovered from a summary file; Wilson CI is exact for those counts
  APPROX       CI from a formula on summary numbers (Hanley-McNeil AUC); replace once predictions exist
  PLACEHOLDER  the per-item file is missing: run the command shown and re-run this script

Writes docs/evidence/ci_report.json and docs/RESULTS_WITH_CI.md (overwritten each run).

Usage (from backend/):  python -m research.compute_ci [--boot 2000]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

import numpy as np  # noqa: E402

from research import stats  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EVID = os.path.join(ROOT, "docs", "evidence")
PRED = os.path.join(EVID, "predictions")
WEIGHTS = os.path.join(ROOT, "backend", "weights")
# DenPAR test films that are copies of a training / validation film (research.split_audit, 2026-10-04)
DENPAR_LEAKED_TEST_FILMS = {"166.jpg", "852.jpg"}


def _csv(name: str) -> list[dict] | None:
    path = os.path.join(PRED, name)
    if not os.path.exists(path):
        return None
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _json(path: str) -> dict:
    return json.load(open(path, encoding="utf-8"))


def row(task, metric, value, ci, n, unit, method, status, pct=False, note=""):
    return {"task": task, "metric": metric, "value": value, "ci95": list(ci) if ci else None, "n": n,
            "unit_of_n": unit, "ci_method": method, "status": status, "pct": pct, "note": note}


def placeholder(task, metric, n, unit, command, value=None, pct=False):
    return row(task, metric, value, None, n, unit, "-", "PLACEHOLDER", pct, f"run: {command}")


# ------------------------------------------------------------------ detector
def detector_rows(boot: int) -> list[dict]:
    out = []
    v1_path = os.path.join(WEIGHTS, "detector_test_metrics_dentex_v1.json")
    m = _json(v1_path if os.path.exists(v1_path) else os.path.join(WEIGHTS, "detector_test_metrics.json"))
    films = _csv("dentex_detector_per_film.csv")
    if films is None:
        cmd = "notebooks/priority1_eval_colab.ipynb on Colab, then copy dentex_detector_per_film.csv here"
        out.append(placeholder("PREVIOUS detector (DENTEX only), DENTEX 63-film split test", "tooth-level F1 (right number)",
                               m["split_sizes"]["test"], "films", cmd, m["tooth_level_F1"], True))
        out.append(placeholder("PREVIOUS detector (DENTEX only), DENTEX 63-film split test", "mAP@0.5",
                               m["split_sizes"]["test"], "films",
                               "bootstrap of mAP needs per-box predictions; report the point value without a CI",
                               m["test_mAP50"], True))
    else:
        out += _detector_from_films("Detector, DENTEX 63-film split test", films, boot)
    films = _csv("dentex_disease_deployed_detector_per_film.csv")
    if films is not None:
        tp, rn = (np.array([int(f[k]) for f in films]) for k in ("teeth_gt", "right_number"))
        n_teeth = int(tp.sum())
        fn_ = lambda i: rn[i].sum() / tp[i].sum()  # noqa: E731
        out.append(row("DEPLOYED detector, DENTEX official disease test (only diseased teeth outlined)",
                       "found with the right FDI number (recall)", float(fn_(np.arange(len(films)))),
                       stats.bootstrap_ci(fn_, len(films), None, boot), len(films),
                       f"films ({n_teeth} diseased teeth)", "film-level bootstrap", "VERIFIED", True,
                       "precision not measurable: healthy teeth are not labelled in this set"))
    # Deployed detector (since 2026-10-04): DENTEX + fine-tuned on AKU folders 1 and 3. Folder 2 was never used
    # for its training, but it is the same hospital, so it is a held-out test, not a different-hospital test.
    films = _csv("aku_folder2_finetuned_detector_per_film.csv")
    if films is None:
        out.append(placeholder("DEPLOYED detector, AKU folder 2 (unseen films, same hospital)",
                               "tooth-level F1 (right number)", 96, "films",
                               'scripts/evaluate_detector_external.py --folders "folder 2" --per-image-csv ...'))
    else:
        out += _detector_from_films("DEPLOYED detector (DENTEX + AKU fine-tune), AKU folder 2: unseen films, same hospital",
                                    films, boot)
    # Previous detector (DENTEX only): the different-hospital result
    films = _csv("aku_detector_per_film.csv")
    if films is not None:
        out += _detector_from_films("PREVIOUS detector (DENTEX only), AKU all 250 films: different hospital", films, boot)
        sub = [f for f in films if f["folder"] == "folder 2"]
        out += _detector_from_films("PREVIOUS detector (DENTEX only), AKU folder 2 (same films as the deployed row)",
                                    sub, boot)
    return out


def _detector_from_films(task: str, films: list[dict], boot: int) -> list[dict]:
    tp, fp, fn, right = (np.array([int(f[k]) for f in films]) for k in ("tp", "fp", "fn", "right_number"))
    n_teeth = int(tp.sum() + fn.sum())

    def f1(idx):
        r, t = right[idx].sum(), tp[idx].sum()
        return 2 * r / (2 * r + 2 * (t - r) + fp[idx].sum() + fn[idx].sum())

    metrics = {
        "detection recall": lambda i: tp[i].sum() / (tp[i].sum() + fn[i].sum()),
        "detection precision": lambda i: tp[i].sum() / (tp[i].sum() + fp[i].sum()),
        "numbering accuracy of detected teeth": lambda i: right[i].sum() / tp[i].sum(),
        "tooth-level F1 with the right FDI number": f1,
    }
    allidx = np.arange(len(films))
    return [row(task, name, float(fn_(allidx)), stats.bootstrap_ci(fn_, len(films), None, boot), len(films),
                f"films ({n_teeth} reference teeth)", "film-level bootstrap", "VERIFIED", True)
            for name, fn_ in metrics.items()]


# ------------------------------------------------------------------ periapical bone loss (DenPAR)
def denpar_rows(boot: int) -> tuple[list[dict], dict | None]:
    teeth = _csv("denpar_test_per_tooth.csv")
    task = "Periapical bone loss, DenPAR test, deployed pipeline"
    if teeth is None:
        cmd = ("DB_MODE=demo python scripts/evaluate_landmarks.py --images <pose>/images/test --labels <pose>/labels/test "
               "--out ../docs/evidence/denpar_test_eval.json --per-tooth-csv ../docs/evidence/predictions/denpar_test_per_tooth.csv")
        return [placeholder(task, "bone-loss MAE (points)", 576, "teeth", cmd, 7.369)], None
    out, staging = [], {}
    for label, keep in (("all 200 films", lambda t: True),
                        ("excluding the 2 test films duplicated in train/val", lambda t: t["image"] not in DENPAR_LEAKED_TEST_FILMS)):
        sel = [t for t in teeth if keep(t)]
        films = sorted({t["image"] for t in sel})
        found = [t for t in sel if t["status"] != "missed"]
        m = [t for t in sel if t["status"] == "measured"]
        film_of = np.array([t["image"] for t in m])
        ref, pred = np.array([float(t["ref_pct"]) for t in m]), np.array([float(t["pred_pct"]) for t in m])
        tname = f"{task} ({label})"
        rec_hit = np.array([t["status"] != "missed" for t in sel])
        rec_film = np.array([t["image"] for t in sel])
        out.append(row(tname, "tooth recall (IoU >= 0.5)", len(found) / len(sel),
                       stats.bootstrap_ci(lambda i: rec_hit[i].mean(), len(sel), rec_film, boot), len(sel),
                       f"labelled teeth in {len(films)} films", "film-cluster bootstrap", "VERIFIED", True))
        mr = stats.mae_report(ref, pred, film_of, boot)
        unit = f"measured teeth in {len(set(film_of))} films"
        out.append(row(tname, "bone-loss MAE (percentage points)", mr["mae"], mr["mae_ci95"], mr["n"], unit,
                       "film-cluster bootstrap", "VERIFIED"))
        out.append(row(tname, "median absolute error (points)", mr["median_abs_error"], mr["median_abs_error_ci95"],
                       mr["n"], unit, "film-cluster bootstrap", "VERIFIED"))
        out.append(row(tname, "within 10 points", mr["within_10_points"], mr["within_10_points_ci95"], mr["n"], unit,
                       "film-cluster bootstrap", "VERIFIED", True))
        sr = stats.stage_report(ref, pred, film_of, boot)
        staging[label] = sr
        out.append(row(tname, "exact stage agreement (I/II/III)", sr["exact_stage_accuracy"], sr["exact_stage_accuracy_ci95"],
                       sr["n"], unit, "film-cluster bootstrap", "VERIFIED", True))
        cov = np.array([t["covered"] == "True" for t in m])
        out.append(row(tname, "90 % interval coverage", float(cov.mean()),
                       stats.bootstrap_ci(lambda i: cov[i].mean(), len(m), film_of, boot), len(m), unit,
                       "film-cluster bootstrap", "VERIFIED", True))
    return out, staging


# ------------------------------------------------------------------ panoramic
def mmopg_rows(boot: int) -> list[dict]:
    m = _json(os.path.join(WEIGHTS, "panoramic_screen_metrics.json"))
    films = _csv("mmopg_screen_per_film.csv")
    out = []
    n = m["test_films"]
    for jaw, j in m["jaws"].items():
        task = f"Panoramic bone-loss screen, {jaw} (MM-OPG test)"
        if films is not None:
            sel = [f for f in films if f["jaw"] == jaw]
            y = np.array([int(f["y"]) for f in sel])
            p = np.array([float(f["prob"]) for f in sel])
            thr = float(sel[0]["threshold_from_val"])
            out.append(row(task, "AUC", stats.auc(y, p), stats.auc_ci_bootstrap(y, p, None, boot), len(y),
                           f"films ({int(y.sum())} with bone loss)", "bootstrap", "VERIFIED"))
            for name, mask, hit in (("sensitivity", y == 1, p >= thr), ("specificity", y == 0, p < thr)):
                k, nn = int(hit[mask].sum()), int(mask.sum())
                out.append(row(task, name, k / nn, stats.wilson(k, nn), nn, "films", "Wilson", "VERIFIED", True))
            continue
        n_pos = int(round(j["test_prevalence"] * n))
        n_neg = n - n_pos
        tp_k, tn_k = int(round(j["test_sensitivity"] * n_pos)), int(round(j["test_specificity"] * n_neg))
        out.append(row(task, "AUC", j["test_auc"], stats.auc_ci_hanley_mcneil(j["test_auc"], n_pos, n_neg), n,
                       f"films ({n_pos} with bone loss)", "Hanley-McNeil (approximation)", "APPROX", False,
                       "replace with the bootstrap: run notebooks/priority1_eval_colab.ipynb on Colab"))
        out.append(row(task, "sensitivity", tp_k / n_pos, stats.wilson(tp_k, n_pos), n_pos, "films with bone loss",
                       "Wilson", "FROM-COUNTS", True))
        out.append(row(task, "specificity", tn_k / n_neg, stats.wilson(tn_k, n_neg), n_neg, "films without",
                       "Wilson", "FROM-COUNTS", True))
    return out


def brar_rows(boot: int) -> tuple[list[dict], dict | None]:
    films = _csv("brar_severity_per_film.csv")
    task = "Panoramic worst-tooth bone loss (BRAR test)"
    if films is None:
        return [placeholder(task, "MAE (points)", 149, "films", "python -m research.export_predictions brar-severity ...",
                            11.367)], None
    m = _json(os.path.join(WEIGHTS, "panoramic_severity_metrics.json"))
    test = [f for f in films if f["split"] == "test"]
    ref, pred = np.array([float(f["ref_pct"]) for f in test]), np.array([float(f["pred_pct"]) for f in test])
    mr = stats.mae_report(ref, pred, None, boot)
    sr = stats.stage_report(ref, pred, None, boot)
    cov = np.abs(pred - ref) <= m["conformal_q90_from_val"]
    unit = "films (1 patient each)"
    return [
        row(task, "worst-tooth MAE (points)", mr["mae"], mr["mae_ci95"], mr["n"], unit, "bootstrap", "VERIFIED"),
        row(task, "median absolute error (points)", mr["median_abs_error"], mr["median_abs_error_ci95"], mr["n"], unit,
            "bootstrap", "VERIFIED"),
        row(task, "exact stage agreement (I/II/III)", sr["exact_stage_accuracy"], sr["exact_stage_accuracy_ci95"], sr["n"],
            unit, "Wilson", "VERIFIED", True),
        row(task, "90 % interval coverage", float(cov.mean()), stats.wilson(int(cov.sum()), len(cov)), len(cov), unit,
            "Wilson", "VERIFIED", True),
    ], sr


# ------------------------------------------------------------------ risk
def risk_rows(boot: int) -> list[dict]:
    people = _csv("nhanes_risk_per_person.csv")
    task = "Clinical risk model (NHANES 2013-14 temporal test)"
    if people is None:
        return [placeholder(task, "AUC", 3855, "people", "python -m research.export_predictions nhanes-risk ...", 0.6504)]
    out = []
    for model in ("with_hba1c", "without_hba1c"):
        sel = [p for p in people if p["model"] == model]
        y = np.array([int(p["y"]) for p in sel])
        p = np.array([float(p["prob"]) for p in sel])
        out.append(row(f"{task}, {model.replace('_', ' ')}", "AUC", stats.auc(y, p), stats.auc_ci_bootstrap(y, p, None, boot),
                       len(y), f"people ({int(y.sum())} with moderate/severe periodontitis)", "bootstrap", "VERIFIED"))
        brier = (p - y) ** 2
        out.append(row(f"{task}, {model.replace('_', ' ')}", "Brier score", float(brier.mean()),
                       stats.bootstrap_ci(lambda i: brier[i].mean(), len(y), None, boot), len(y), "people", "bootstrap",
                       "VERIFIED"))
    return out


# ------------------------------------------------------------------ report
def _fmt(r: dict) -> str:
    if r["value"] is None:
        return "—"
    s, unit = (100, " %") if r["pct"] else (1, "")
    v = f"{r['value'] * s:.1f}{unit}" if r["pct"] else f"{r['value']:.3f}" if r["value"] < 1.5 else f"{r['value']:.2f}"
    if not r["ci95"]:
        return v + " (no CI yet)"
    lo, hi = (x * s for x in r["ci95"])
    d = 1 if r["pct"] or r["value"] >= 1.5 else 3
    return f"{v} ({lo:.{d}f} – {hi:.{d}f})"


def _cm_md(title: str, sr: dict) -> str:
    cm = sr["confusion_rows_reference_cols_predicted"]
    lines = [f"**{title}** (n = {sr['n']}" + (f" teeth in {sr['n_clusters']} films" if sr["n_clusters"] != sr["n"] else " films")
             + ")", "", "| Reference ↓ / Predicted → | I | II | III | Total |", "|---|---|---|---|---|"]
    for lab, r in zip(sr["labels"], cm):
        lines.append(f"| **{lab}** | " + " | ".join(str(x) for x in r) + f" | {sum(r)} |")
    pct = lambda v, ci: f"{v * 100:.1f} % (95 % CI {ci[0] * 100:.1f} – {ci[1] * 100:.1f})"  # noqa: E731
    num = lambda v, ci: f"{v:.3f} (95 % CI {ci[0]:.3f} – {ci[1]:.3f})"  # noqa: E731
    lines += ["", f"- Exact stage: {pct(sr['exact_stage_accuracy'], sr['exact_stage_accuracy_ci95'])}",
              f"- Within one stage: {pct(sr['within_one_stage_accuracy'], sr['within_one_stage_accuracy_ci95'])}",
              f"- Weighted kappa, linear: {num(sr['kappa_linear'], sr['kappa_linear_ci95'])}",
              f"- Weighted kappa, quadratic: {num(sr['kappa_quadratic'], sr['kappa_quadratic_ci95'])}", ""]
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--boot", type=int, default=2000)
    args = ap.parse_args(argv)
    den, den_stage = denpar_rows(args.boot)
    brar, brar_stage = brar_rows(args.boot)
    rows = detector_rows(args.boot) + den + mmopg_rows(args.boot) + brar + risk_rows(args.boot)
    report = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(), "bootstrap_resamples": args.boot,
              "rows": rows, "staging": {"periapical_denpar": den_stage, "panoramic_brar": brar_stage}}
    json.dump(report, open(os.path.join(EVID, "ci_report.json"), "w", encoding="utf-8"), indent=2, default=float)

    md = ["# Results with sample sizes and 95 % confidence intervals", "",
          f"_Generated by `python -m research.compute_ci` on {report['generated'][:10]} "
          f"({args.boot} bootstrap resamples, seed 0). Do not edit by hand; re-run the script._", "",
          "Status: **VERIFIED** = recomputed from per-item predictions of the deployed model · **FROM-COUNTS** = exact "
          "counts from a summary file · **APPROX** = formula on summary numbers · **PLACEHOLDER** = not yet run.", "",
          "Teeth from the same film are not independent, so every per-tooth interval resamples whole films "
          "(cluster bootstrap). That makes those intervals wider, and honest.", "",
          "| Task | Metric | Value (95 % CI) | n | CI method | Status |", "|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['task']} | {r['metric']} | {_fmt(r)} | {r['n']} {r['unit_of_n']} | {r['ci_method']} | "
                  f"{r['status']}{' — ' + r['note'] if r['note'] else ''} |")
    md += ["", "## Staging agreement (Priority 1, item 4)", ""]
    if den_stage:
        for label, sr in den_stage.items():
            md.append(_cm_md(f"Periapical, DenPAR test — {label}", sr))
    else:
        md.append("Periapical: PLACEHOLDER (per-tooth predictions not yet exported).")
    md.append(_cm_md("Panoramic, BRAR test (worst tooth per patient)", brar_stage) if brar_stage
              else "Panoramic: PLACEHOLDER.")
    md += ["Stage IV needs the number of teeth lost to periodontitis, which a radiograph does not give, so the "
           "comparison is over I / II / III only. Bands: I < 15 %, II 15–33 %, III > 33 % of root length.", ""]
    path = os.path.join(ROOT, "docs", "RESULTS_WITH_CI.md")
    open(path, "w", encoding="utf-8").write("\n".join(md))
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows consoles default to cp1252
    print("\n".join(md))
    print(f"\nwritten: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
