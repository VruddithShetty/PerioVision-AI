"""Thesis analyses from existing per-item predictions: where the model fails, how landmark noise drives bone-loss error,
how accuracy rises when uncertain teeth are referred to a dentist, and a gallery of good / typical / failure cases.

Inputs (no model is run):
  docs/evidence/predictions/denpar_test_per_tooth.csv   app-path DenPAR test predictions (corrected reference)
  docs/evidence/predictions/brar_severity_per_film.csv  panoramic worst-tooth predictions (BRAR test)
  DenPAR film metadata (arch / site) and the corrected reference labels (scripts/convert_denpar.py output)
Outputs: docs/ANALYSES.md, docs/figures/*.png (regenerated on every run; do not edit by hand).

Usage (from backend/):
    python -m research.thesis_analyses --denpar ~/Downloads/DenPAR --labels ~/Downloads/DenPAR/pose_dataset_fixed
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))           # backend/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from research import stats  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PRED = os.path.join(ROOT, "docs", "evidence", "predictions")
FIG = os.path.join(ROOT, "docs", "figures")
# validated categorical palette (dataviz reference: blue, orange, aqua) + text tokens
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
BOOT = 2000


def _teeth():
    rows = [r for r in csv.DictReader(open(os.path.join(PRED, "denpar_test_per_tooth.csv"), encoding="utf-8"))
            if r["status"] == "measured"]
    for r in rows:
        r["err"] = abs(float(r["pred_pct"]) - float(r["ref_pct"]))
        r["ok"] = r["pred_stage"] == r["ref_stage"]
    return rows


def _group_table(rows, key, order=None, cluster="image"):
    groups = {}
    for r in rows:
        groups.setdefault(key(r), []).append(r)
    out = []
    for g in (order or sorted(groups)):
        if g not in groups:
            continue
        rs = groups[g]
        err = np.array([r["err"] for r in rs])
        ok = np.array([r["ok"] for r in rs], float)
        cl = np.array([r[cluster] for r in rs]) if cluster else None
        out.append({"group": g, "n": len(rs), "films": len({r.get("image", r.get("film")) for r in rs}),
                    "mae": err.mean(), "mae_ci": stats.bootstrap_ci(lambda i: err[i].mean(), len(err), cl, BOOT),
                    "stage": ok.mean(), "stage_ci": stats.bootstrap_ci(lambda i: ok[i].mean(), len(ok), cl, BOOT)})
    return out


def _md_table(title, rows, unit="teeth"):
    lines = [f"| {title} | {unit} (films) | Bone-loss error, points (95 % CI) | Stage agreement (95 % CI) |",
             "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['group']} | {r['n']} ({r['films']}) | {r['mae']:.2f} ({r['mae_ci'][0]:.2f}-{r['mae_ci'][1]:.2f}) | "
                     f"{100 * r['stage']:.1f} % ({100 * r['stage_ci'][0]:.1f}-{100 * r['stage_ci'][1]:.1f}) |")
    return "\n".join(lines)


# ------------------------------------------------------------------ 1. error analysis
def error_analysis(denpar: str, teeth) -> str:
    import pandas as pd

    meta = pd.read_excel(os.path.join(denpar, "Dataset", "Characteristics of radiographs included.xlsx"))
    meta = {f"{int(i)}.jpg": (a, s) for i, a, s in zip(meta["id"], meta["Arch"], meta["Site"])}
    imgdir = os.path.join(denpar, "Dataset", "Testing", "Images")
    quality = {}
    for f in {r["image"] for r in teeth}:
        g = cv2.imread(os.path.join(imgdir, f), cv2.IMREAD_GRAYSCALE)
        g = g.reshape(g.shape[:2])
        quality[f] = (float(cv2.Laplacian(g, cv2.CV_64F).var()), float(g.std()))
    sharp = np.array([quality[f][0] for f in quality])
    contrast = np.array([quality[f][1] for f in quality])
    s_cut, c_cut = np.quantile(sharp, [1 / 3, 2 / 3]), np.quantile(contrast, [1 / 3, 2 / 3])
    tert = lambda v, cuts: "low" if v <= cuts[0] else ("middle" if v <= cuts[1] else "high")  # noqa: E731
    out = ["## 1. Where the periapical model makes its errors",
           "",
           f"DenPAR test, app pipeline, corrected reference: {len(teeth)} measured teeth in "
           f"{len({r['image'] for r in teeth})} films. Intervals resample whole films. Groups with overlapping intervals "
           "are not shown to differ.", ""]
    out += [_md_table("Arch", _group_table(teeth, lambda r: meta.get(r["image"], ("unknown",))[0], ["Upper", "Lower"])), ""]
    out += [_md_table("Region", _group_table(teeth, lambda r: "Anterior" if meta.get(r["image"], ("", ""))[1] == "Anterior"
                                             else "Posterior (left / right)", ["Anterior", "Posterior (left / right)"])), ""]
    out += [_md_table("Reference stage", _group_table(teeth, lambda r: r["ref_stage"], ["I", "II", "III"])), ""]
    out += [_md_table("Image sharpness (tertile)", _group_table(teeth, lambda r: tert(quality[r["image"]][0], s_cut),
                                                                ["low", "middle", "high"])), ""]
    out += [_md_table("Image contrast (tertile)", _group_table(teeth, lambda r: tert(quality[r["image"]][1], c_cut),
                                                               ["low", "middle", "high"])), ""]
    out += ["DenPAR does not label restorations, implants or overlapping teeth, so those groups cannot be measured on "
            "periapical films here. They are measured on panoramic films below (BRAR records them per patient).", ""]

    films = [r for r in csv.DictReader(open(os.path.join(PRED, "brar_severity_per_film.csv"), encoding="utf-8"))
             if r["split"] == "test"]
    for r in films:
        r["err"] = abs(float(r["pred_pct"]) - float(r["ref_pct"]))
        r["ok"] = stats.stage_of(float(r["pred_pct"])) == stats.stage_of(float(r["ref_pct"]))
        r["image"] = r["film"]
    out += ["### Panoramic worst-tooth estimate (BRAR test, one film per patient)", ""]
    for title, key, order in (
            ("Missing teeth", lambda r: "none" if int(r["missing_teeth"]) == 0 else "1 or more", ["none", "1 or more"]),
            ("Implants", lambda r: "none" if int(r["implants"]) == 0 else "1 or more", ["none", "1 or more"]),
            ("Residual roots", lambda r: "none" if int(r["residual_roots"]) == 0 else "1 or more", ["none", "1 or more"]),
            ("Age", lambda r: "under 40" if int(r["age"]) < 40 else ("40-59" if int(r["age"]) < 60 else "60 and over"),
             ["under 40", "40-59", "60 and over"]),
            ("Reference stage", lambda r: stats.stage_of(float(r["ref_pct"])), ["I", "II", "III"])):
        out += [_md_table(title, _group_table(films, key, order, cluster=None), unit="patients"), ""]
    out += ["**Reading the tables.**",
            "- **Severity is the main driver.** Error rises with the reference stage on both film types (periapical "
            "4.8 / 7.3 / 10.6 points for stage I / II / III; panoramic 6.5 / 6.9 / 19.5): severe bone loss is "
            "underestimated, which the asymmetric uncertainty interval accounts for.",
            "- **Stage II is the hardest stage to call** (about half correct on both film types), because its band is "
            "only 18 points wide.",
            "- **Missing teeth, residual roots and older age** go with much larger panoramic errors, but those patients "
            "also have more severe disease, so these groups are confounded with severity and are not separate effects.",
            "- **Image quality:** high-contrast films show a somewhat higher error than low-contrast ones, with "
            "overlapping intervals (a hint, not a finding); sharpness shows no clear pattern. Upper vs lower arch and "
            "front vs back teeth do not differ clearly.",
            "- Small groups (implants: 15 patients; residual roots: 12) have very wide intervals; do not read a "
            "difference into them.", ""]
    return "\n".join(out)


# ------------------------------------------------------------------ 2. landmark noise
def noise_sensitivity(labels: str) -> tuple[str, str]:
    from evaluate_landmarks import read_labels

    rng = np.random.default_rng(0)  # audit-ok: seeded simulation
    teeth = []
    for lab in sorted(os.listdir(os.path.join(labels, "labels", "test"))):
        img = os.path.join(labels, "images", "test", lab.replace(".txt", ".jpg"))
        g = cv2.imread(img, cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        h, w = g.shape[:2]
        for t in read_labels(os.path.join(labels, "labels", "test", lab), w, h):
            teeth.append({k: np.array(t[k], float) for k in ("cej", "root_apex", "bone_crest")})

    def pct(c, a, b):
        root = a - c
        return np.clip(np.sum((b - c) * root, 1) / np.sum(root * root, 1) * 100, 0, 100)

    C = np.stack([t["cej"] for t in teeth])
    A = np.stack([t["root_apex"] for t in teeth])
    K = np.stack([t["bone_crest"] for t in teeth])
    L = np.linalg.norm(A - C, axis=1, keepdims=True)
    base = pct(C, A, K)
    levels = np.arange(0, 21, 2.0)
    curves = {"CEJ": [], "bone crest": [], "apex": [], "all three": []}
    for s in levels:
        def noisy(P):
            return P + rng.normal(0, 1, P.shape) * L * s / 100.0
        res = {"CEJ": pct(noisy(C), A, K), "bone crest": pct(C, A, noisy(K)), "apex": pct(C, noisy(A), K),
               "all three": pct(noisy(C), noisy(A), noisy(K))}
        for k, v in res.items():
            curves[k].append(float(np.mean(np.abs(v - base))))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    styles = {"CEJ": (BLUE, "-"), "bone crest": (ORANGE, "--"), "apex": (AQUA, ":")}
    for k, (col, ls) in styles.items():
        ax.plot(levels, curves[k], color=col, lw=2, ls=ls, marker="o", ms=4, label=k)
        ax.annotate(k, (levels[-1], curves[k][-1]), xytext=(6, 0), textcoords="offset points", va="center",
                    color=INK2, fontsize=9)
    ax.set_xlabel("Landmark noise, SD as % of root length", color=INK2)
    ax.set_ylabel("Bone-loss error caused (points)", color=INK2)
    ax.set_title("How each landmark's error turns into bone-loss error", color=INK, loc="left", fontsize=11)
    ax.grid(True, color=GRID, lw=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    ax.tick_params(colors=INK2)
    ax.legend(frameon=False, loc="upper left")
    ax.set_xlim(0, levels[-1] + 3.5)
    fig.tight_layout()
    path = os.path.join(FIG, "landmark_noise_sensitivity.png")
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    rows = ["| Noise SD (% of root length) | CEJ | Bone crest | Apex | All three |", "|---|---|---|---|---|"]
    for i, s in enumerate(levels):
        if s in (0, 4, 6, 10, 14, 20):
            rows.append(f"| {s:.0f} | {curves['CEJ'][i]:.2f} | {curves['bone crest'][i]:.2f} | {curves['apex'][i]:.2f} | "
                        f"{curves['all three'][i]:.2f} |")
    text = ["## 2. How landmark error turns into bone-loss error", "",
            f"Each landmark of the {len(teeth)} reference test teeth is moved by random noise of a given size "
            "(Gaussian, SD as % of the tooth's root length), one landmark at a time, and the resulting change in "
            "bone loss is measured (points). Seeded simulation on the specialist labels; no model involved.", "",
            "![Landmark noise sensitivity](figures/landmark_noise_sensitivity.png)", "", *rows, "",
            "**Reading it.** The bone crest matters most, then the CEJ, because bone loss is their distance along the "
            "root; the apex only scales that distance (a 10 % apex error costs under 2 points). The deployed model's "
            "measured same-side errors are about 6 % (CEJ), 10 % (crest) and 4.5 % (apex) of root length; in this "
            "simulation errors of that size produce several points of bone-loss error, the same order as the 6.6 "
            "points measured on the test set (real errors are not purely random, so this is a guide, not an exact "
            "decomposition). Improving the **crest** point is therefore the most direct way to lower the error, and "
            "to make progression detection more sensitive.", ""]
    return "\n".join(text), path


# ------------------------------------------------------------------ 3. accuracy vs coverage (refer to a dentist)
def coverage(teeth) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    hw = np.array([float(r["half_width"]) if r["half_width"] not in ("", "None") else np.inf for r in teeth])
    err = np.array([r["err"] for r in teeth])
    ok = np.array([r["ok"] for r in teeth], float)
    films = np.array([r["image"] for r in teeth])
    order = np.argsort(hw, kind="stable")                     # most confident (narrowest interval) first
    covs = np.arange(1.0, 0.29, -0.05)
    mae_c, st_c = [], []
    for c in covs:
        keep = order[: max(1, int(round(c * len(order))))]
        mae_c.append(err[keep].mean())
        st_c.append(ok[keep].mean())
    rows = ["| Teeth reported automatically | Referred to a dentist | Bone-loss error (95 % CI) | Stage agreement (95 % CI) | "
            "Interval half-width cut-off |", "|---|---|---|---|---|"]
    for c in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
        keep = order[: int(round(c * len(order)))]
        e, o, f = err[keep], ok[keep], films[keep]
        cut = hw[keep].max()
        rows.append(f"| {100 * c:.0f} % | {100 * (1 - c):.0f} % | {e.mean():.2f} "
                    f"({stats.bootstrap_ci(lambda i: e[i].mean(), len(e), f, BOOT)[0]:.2f}-"
                    f"{stats.bootstrap_ci(lambda i: e[i].mean(), len(e), f, BOOT)[1]:.2f}) | {100 * o.mean():.1f} % "
                    f"({100 * stats.bootstrap_ci(lambda i: o[i].mean(), len(o), f, BOOT)[0]:.1f}-"
                    f"{100 * stats.bootstrap_ci(lambda i: o[i].mean(), len(o), f, BOOT)[1]:.1f}) | "
                    f"{'none' if c == 1.0 or not np.isfinite(cut) else f'up to {cut:.1f} points'} |")
    for name, ys, ylab, fname in (("Bone-loss error", mae_c, "Mean absolute error (points)", "coverage_error.png"),
                                  ("Stage agreement", [100 * v for v in st_c], "Exact stage agreement (%)",
                                   "coverage_stage.png")):
        fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
        fig.patch.set_facecolor(SURFACE)
        ax.set_facecolor(SURFACE)
        ax.plot(100 * covs, ys, color=BLUE, lw=2, marker="o", ms=4)
        ax.invert_xaxis()
        ax.set_xlabel("Share of teeth reported automatically (%)  - the rest go to a dentist", color=INK2)
        ax.set_ylabel(ylab, color=INK2)
        ax.set_title(f"{name} when the least certain teeth are referred", color=INK, loc="left", fontsize=11)
        ax.grid(True, color=GRID, lw=0.8)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_color(GRID)
        ax.tick_params(colors=INK2)
        fig.tight_layout()
        fig.savefig(os.path.join(FIG, fname), facecolor=SURFACE)
        plt.close(fig)
    return "\n".join(["## 3. Accuracy versus coverage: when to refer a tooth to a dentist", "",
                      "Teeth are ordered by the width of their calibrated uncertainty interval (narrow = the model is "
                      "consistent with itself). Reporting only the most certain teeth automatically and referring the "
                      "rest shows how much accuracy the referral rule buys. Same test teeth as above; intervals resample "
                      "whole films.", "",
                      "![Error vs coverage](figures/coverage_error.png)", "",
                      "![Stage agreement vs coverage](figures/coverage_stage.png)", "", *rows, "",
                      "**Reading it.** Referring the least certain 10 % of teeth lowers the error of the rest from "
                      "6.6 to 5.8 points; referring more helps little (5.4 points when half are referred), and stage "
                      "agreement rises only from 76 % to 79 %. The interval width is a real but partial confidence "
                      "score: it flags the worst teeth, not every wrong one. A practical rule is therefore: report "
                      "automatically only teeth with a 90 % interval half-width up to about 29 points, and refer the "
                      "rest. The app goes further and already sends every tooth whose stage is uncertain (more than "
                      "one stage in its prediction set) to dentist review.", ""])


# ------------------------------------------------------------------ 4. gallery
def gallery(labels: str, teeth) -> str:
    from evaluate_landmarks import read_labels

    by_film = {}
    for r in teeth:
        by_film.setdefault(r["image"], []).append(r)
    film_err = sorted(((np.mean([r["err"] for r in rs]), f) for f, rs in by_film.items() if len(rs) >= 2))
    picks = {"good": film_err[:3], "typical": film_err[len(film_err) // 2 - 1: len(film_err) // 2 + 2],
             "failure": film_err[-3:]}
    out = ["## 4. Gallery: good, typical and failure cases", "",
           "Each panel shows a DenPAR test film (CC BY 4.0) with, per measured tooth, the specialist reference points "
           "as filled circles (blue CEJ, orange bone crest, aqua apex) and the model's points as white crosses joined "
           "to them by a thin line. The caption gives the film's mean bone-loss error. Films were chosen by error rank "
           "(lowest three, middle three, highest three), not by hand.", ""]
    colors = {"cej": (214, 120, 42), "bone_crest": (52, 104, 235), "root_apex": (122, 175, 27)}     # BGR of the palette
    for kind, items in picks.items():
        out += [f"### {kind.capitalize()} cases", ""]
        for e, f in items:
            img = cv2.imread(os.path.join(labels, "images", "test", f))
            h, w = img.shape[:2]
            refs = read_labels(os.path.join(labels, "labels", "test", f.replace(".jpg", ".txt")), w, h)
            r_ = max(4, w // 160)
            for r in by_film[f]:
                ref = refs[int(r["tooth_index"])]
                for k, col in colors.items():
                    p = np.array(ref[k])
                    q = p + np.array([float(r[f"{k}_dx_px"]), float(r[f"{k}_dy_px"])])
                    cv2.line(img, tuple(int(v) for v in p), tuple(int(v) for v in q), (235, 235, 235), 1, cv2.LINE_AA)
                    cv2.circle(img, tuple(int(v) for v in p), r_, col, -1, cv2.LINE_AA)
                    cv2.drawMarker(img, tuple(int(v) for v in q), (255, 255, 255), cv2.MARKER_TILTED_CROSS, 3 * r_, 2)
            scale = 900 / w
            img = cv2.resize(img, (900, int(h * scale)), interpolation=cv2.INTER_AREA)
            name = f"gallery_{kind}_{f.replace('.jpg', '')}.jpg"
            cv2.imwrite(os.path.join(FIG, name), img, [cv2.IMWRITE_JPEG_QUALITY, 82])
            stages = ", ".join(f"{r['ref_stage']}->{r['pred_stage']}" for r in by_film[f])
            out += [f"![{kind} case, film {f}](figures/{name})", "",
                    f"Film `{f}`: mean error {e:.1f} points over {len(by_film[f])} teeth; stage reference->model: "
                    f"{stages}.", ""]
    out += ["**Reading it.** In the failure cases the model places the bone crest too far toward the crown on teeth "
            "with deep bone loss (the severe-case underestimation measured above), and one failure film is taken at an "
            "unusual sideways orientation. In the good and typical cases the points sit close to the specialist's. "
            "Look at these panels before trusting a single number on a severely affected tooth.", ""]
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--denpar", default="~/Downloads/DenPAR")
    ap.add_argument("--labels", default="~/Downloads/DenPAR/pose_dataset_fixed")
    args = ap.parse_args(argv)
    denpar, labels = os.path.expanduser(args.denpar), os.path.expanduser(args.labels)
    os.makedirs(FIG, exist_ok=True)
    teeth = _teeth()
    parts = [f"# Thesis analyses\n\n_Generated by `python -m research.thesis_analyses` on {dt.date.today().isoformat()}"
             f" from the files in `docs/evidence/predictions/`. Do not edit by hand; re-run the script._\n",
             error_analysis(denpar, teeth), noise_sensitivity(labels)[0], coverage(teeth), gallery(labels, teeth)]
    path = os.path.join(ROOT, "docs", "ANALYSES.md")
    open(path, "w", encoding="utf-8").write("\n".join(parts))
    print("written", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
