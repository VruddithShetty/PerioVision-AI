"""Small, dependency-light statistics for honest reporting: sample sizes, 95 % confidence intervals,
staging agreement (confusion matrix, exact / within-one-stage accuracy, weighted kappa).

Why each method
  * Proportions with one independent unit per row (films, people): Wilson score interval. It behaves
    well near 0 % / 100 % and for small n, unlike the "p +/- 1.96 SE" textbook interval.
  * Anything measured per TOOTH: teeth in the same film are correlated, so a tooth-level Wilson
    interval would be too narrow. Use the cluster (film-level) bootstrap: resample whole films with
    replacement, recompute the metric, take the 2.5 / 97.5 percentiles.
  * AUC: bootstrap (stratified by class, or by cluster when one film gives two jaws). Hanley & McNeil
    (Radiology 1982;143:29-36) is provided only for when per-film predictions are not available yet,
    and is labelled as an approximation.
  * Weighted kappa (Cohen 1968): linear and quadratic weights over ordered stages I < II < III.

All functions take plain numpy arrays / lists. Nothing here reads files.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

import numpy as np

Z95 = 1.959963984540054
STAGES = ("I", "II", "III")


# ------------------------------------------------------------------ proportions
def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95 % Wilson score interval for k successes out of n."""
    if n <= 0:
        return (float("nan"), float("nan"))
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


# ------------------------------------------------------------------ bootstrap
def bootstrap_ci(metric: Callable[[np.ndarray], float], n_items: int, clusters: Sequence | None = None,
                 n_boot: int = 2000, seed: int = 0, alpha: float = 0.05) -> tuple[float, float]:
    """Percentile bootstrap CI for metric(indices).

    `metric` receives an index array into the item list and returns a number. With `clusters` (one
    label per item, e.g. the film each tooth comes from), whole clusters are resampled, which keeps
    within-film correlation and gives an honest (wider) interval."""
    rng = np.random.default_rng(seed)
    if clusters is None:
        groups = [np.array([i]) for i in range(n_items)]
    else:
        labels = np.asarray(clusters)
        _, inv = np.unique(labels, return_inverse=True)
        groups = [np.flatnonzero(inv == g) for g in range(inv.max() + 1)]
    stats = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(groups), len(groups))
        idx = np.concatenate([groups[g] for g in pick])
        v = metric(idx)
        if v is not None and np.isfinite(v):
            stats.append(v)
    if not stats:
        return (float("nan"), float("nan"))
    lo, hi = np.percentile(stats, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return (float(lo), float(hi))


# ------------------------------------------------------------------ AUC
def auc(y: Sequence[int], p: Sequence[float]) -> float:
    """Mann-Whitney AUC with ties counted as one half."""
    y, p = np.asarray(y), np.asarray(p, float)
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    allv = np.concatenate([pos, neg])[order]
    ranks = np.empty(len(allv))
    i = 0
    while i < len(allv):                       # average ranks for ties
        j = i
        while j + 1 < len(allv) and allv[j + 1] == allv[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2 + 1
        i = j + 1
    r = np.empty(len(allv))
    r[order] = ranks
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def auc_ci_bootstrap(y, p, clusters=None, n_boot: int = 2000, seed: int = 0) -> tuple[float, float]:
    y, p = np.asarray(y), np.asarray(p, float)
    return bootstrap_ci(lambda idx: auc(y[idx], p[idx]), len(y), clusters, n_boot, seed)


def auc_ci_hanley_mcneil(a: float, n_pos: int, n_neg: int, z: float = Z95) -> tuple[float, float]:
    """APPROXIMATE CI from a reported AUC and class counts only. Replace with the bootstrap once
    per-item predictions exist."""
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    se = math.sqrt((a * (1 - a) + (n_pos - 1) * (q1 - a * a) + (n_neg - 1) * (q2 - a * a)) / (n_pos * n_neg))
    return (max(0.0, a - z * se), min(1.0, a + z * se))


# ------------------------------------------------------------------ staging agreement
def stage_of(pct: float) -> str:
    """Same bands as app/ml/measurement/staging.py and scripts/train_panoramic_boneloss.py."""
    return "I" if pct < 15 else "II" if pct <= 33 else "III"


def confusion(ref: Sequence[str], pred: Sequence[str], labels=STAGES) -> np.ndarray:
    """Rows = reference stage, columns = predicted stage."""
    m = np.zeros((len(labels), len(labels)), int)
    pos = {s: i for i, s in enumerate(labels)}
    for r, p in zip(ref, pred):
        m[pos[r], pos[p]] += 1
    return m


def weighted_kappa(ref: Sequence[str], pred: Sequence[str], weights: str = "quadratic", labels=STAGES) -> float:
    """Cohen's weighted kappa. 1 = perfect, 0 = chance-level agreement."""
    m = confusion(ref, pred, labels).astype(float)
    n = m.sum()
    if n == 0:
        return float("nan")
    k = len(labels)
    i, j = np.meshgrid(np.arange(k), np.arange(k), indexing="ij")
    w = np.abs(i - j) / (k - 1) if weights == "linear" else ((i - j) / (k - 1)) ** 2
    expected = np.outer(m.sum(1), m.sum(0)) / n
    denom = (w * expected).sum()
    return float(1 - (w * m).sum() / denom) if denom > 0 else float("nan")


def stage_report(ref_pct, pred_pct, clusters=None, n_boot: int = 2000, seed: int = 0) -> dict:
    """Full staging block for one task: n, confusion matrix, exact / within-one accuracy, kappas, CIs."""
    ref = [stage_of(x) for x in ref_pct]
    pred = [stage_of(x) for x in pred_pct]
    ri = np.array([STAGES.index(s) for s in ref])
    pi = np.array([STAGES.index(s) for s in pred])
    n = len(ref)
    exact = float(np.mean(ri == pi))
    within1 = float(np.mean(np.abs(ri - pi) <= 1))
    ref_a, pred_a = np.array(ref), np.array(pred)

    def ci(fn):
        return bootstrap_ci(fn, n, clusters, n_boot, seed)

    out = {
        "n": n,
        "n_clusters": int(len(set(clusters))) if clusters is not None else n,
        "labels": list(STAGES),
        "confusion_rows_reference_cols_predicted": confusion(ref, pred).tolist(),
        "exact_stage_accuracy": exact,
        "exact_stage_accuracy_ci95": ci(lambda idx: float(np.mean(ri[idx] == pi[idx]))),
        "within_one_stage_accuracy": within1,
        "within_one_stage_accuracy_ci95": ci(lambda idx: float(np.mean(np.abs(ri[idx] - pi[idx]) <= 1))),
        "kappa_linear": weighted_kappa(ref, pred, "linear"),
        "kappa_linear_ci95": ci(lambda idx: weighted_kappa(ref_a[idx], pred_a[idx], "linear")),
        "kappa_quadratic": weighted_kappa(ref, pred, "quadratic"),
        "kappa_quadratic_ci95": ci(lambda idx: weighted_kappa(ref_a[idx], pred_a[idx], "quadratic")),
        "per_reference_stage_n": {s: int(np.sum(ri == k)) for k, s in enumerate(STAGES)},
    }
    if clusters is None:   # independent units: Wilson is exact enough and does not depend on the seed
        out["exact_stage_accuracy_ci95"] = wilson(int(np.sum(ri == pi)), n)
        out["within_one_stage_accuracy_ci95"] = wilson(int(np.sum(np.abs(ri - pi) <= 1)), n)
    return out


def mae_report(ref, pred, clusters=None, n_boot: int = 2000, seed: int = 0) -> dict:
    err = np.abs(np.asarray(pred, float) - np.asarray(ref, float))
    return {
        "n": int(len(err)),
        "mae": float(err.mean()),
        "mae_ci95": bootstrap_ci(lambda idx: float(err[idx].mean()), len(err), clusters, n_boot, seed),
        "median_abs_error": float(np.median(err)),
        "median_abs_error_ci95": bootstrap_ci(lambda idx: float(np.median(err[idx])), len(err), clusters, n_boot, seed),
        "within_10_points": float(np.mean(err <= 10)),
        "within_10_points_ci95": bootstrap_ci(lambda idx: float(np.mean(err[idx] <= 10)), len(err), clusters,
                                              n_boot, seed),
    }


def fmt_ci(value: float, ci: tuple[float, float], pct: bool = False, digits: int = 1) -> str:
    """'73.3 % (95 % CI 68.9-77.2)' or '7.37 (95 % CI 6.8-8.0)'."""
    if value is None or not np.isfinite(value):
        return "n/a"
    s = 100 if pct else 1
    unit = " %" if pct else ""
    return f"{value * s:.{digits}f}{unit} (95% CI {ci[0] * s:.{digits}f}-{ci[1] * s:.{digits}f})"
