"""The thesis statistics agree with reference implementations (scikit-learn) and textbook values."""
import numpy as np
import pytest
from sklearn.metrics import cohen_kappa_score, roc_auc_score

from research import stats


def test_wilson_matches_textbook_example():
    # Newcombe (Stat Med 1998) example: 81 / 263 -> 0.2553 to 0.3662
    lo, hi = stats.wilson(81, 263)
    assert lo == pytest.approx(0.2553, abs=1e-3) and hi == pytest.approx(0.3662, abs=1e-3)
    assert stats.wilson(0, 10)[0] == pytest.approx(0.0) and stats.wilson(10, 10)[1] == pytest.approx(1.0)


def test_auc_matches_sklearn_including_ties():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 300)
    p = np.round(rng.random(300) + 0.3 * y, 1)          # rounded -> many ties
    assert stats.auc(y, p) == pytest.approx(roc_auc_score(y, p), abs=1e-12)


@pytest.mark.parametrize("weights", ["linear", "quadratic"])
def test_weighted_kappa_matches_sklearn(weights):
    rng = np.random.default_rng(1)
    ref = rng.choice(stats.STAGES, 200)
    pred = np.where(rng.random(200) < 0.7, ref, rng.choice(stats.STAGES, 200))
    assert stats.weighted_kappa(ref, pred, weights) == pytest.approx(
        cohen_kappa_score(ref, pred, weights=weights, labels=list(stats.STAGES)), abs=1e-12)


def test_stage_bands_match_the_app():
    from app.ml.measurement.staging import stage_for_pct

    for pct in (0, 14.99, 15, 20, 33, 33.01, 80):
        assert stats.stage_of(pct) == stage_for_pct(pct)


def test_cluster_bootstrap_is_wider_than_naive_for_correlated_teeth():
    """Teeth in one film share errors; the film-level bootstrap must reflect that."""
    rng = np.random.default_rng(2)
    film_effect = np.repeat(rng.normal(0, 5, 50), 6)
    err = np.abs(film_effect + rng.normal(0, 1, 300))
    films = np.repeat(np.arange(50), 6)
    naive = stats.bootstrap_ci(lambda i: err[i].mean(), 300)
    clustered = stats.bootstrap_ci(lambda i: err[i].mean(), 300, clusters=films)
    assert (clustered[1] - clustered[0]) > 1.5 * (naive[1] - naive[0])


def test_stage_report_confusion_and_within_one():
    ref = [5, 20, 40, 40, 10]     # I, II, III, III, I
    pred = [5, 40, 40, 5, 20]     # I, III, III, I, II
    r = stats.stage_report(ref, pred, n_boot=200)
    assert r["confusion_rows_reference_cols_predicted"] == [[1, 1, 0], [0, 0, 1], [1, 0, 1]]
    assert r["exact_stage_accuracy"] == pytest.approx(2 / 5)
    assert r["within_one_stage_accuracy"] == pytest.approx(4 / 5)   # only III -> I is two stages off
