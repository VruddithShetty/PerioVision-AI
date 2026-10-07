"""Same-site (paired) change detection: repeatability decides, sides are compared with their own side."""
import pytest

from app.services import progression_service as ps


def _visit(date, sites, pct, align=0.95):
    tooth = {"tooth_id": "P1", "tooth_id_source": "positional_estimate", "bbox": [100, 100, 150, 300],
             "bone_loss_pct": pct, "site_bone_loss_pct": sites, "uncertainty": {"half_width": 19.0}}
    return {"analysis_id": date, "visit_date": date, "teeth": [tooth], "image_size": [400, 400], "mode": "live",
            "image_type": "periapical", "alignment": {"status": "success", "confidence": align,
                                                      "matrix_prev_to_curr": [[1, 0, 0], [0, 1, 0]]}}


@pytest.fixture()
def calibrated(monkeypatch):
    monkeypatch.setattr(ps, "change_calibration", lambda: {"change_threshold_points": 4.0})


def test_a_same_site_change_above_repeatability_is_detected(calibrated):
    prev = _visit("2025-01-01", {"left": 12.0, "right": 20.0}, 20.0)
    curr = _visit("2026-01-01", {"left": 12.5, "right": 27.0}, 27.0)
    c = ps.compare_visits(prev, curr)[0]
    assert c["change_rule"] == "paired_site_repeatability"
    assert c["change_detectable"] and c["delta_pct"] == 7.0 and c["label"] == "rapidly progressing"
    assert c["site_deltas_pct"] == {"left": 0.5, "right": 7.0}


def test_noise_below_threshold_is_not_progression(calibrated):
    prev = _visit("2025-01-01", {"left": 12.0, "right": 20.0}, 20.0)
    curr = _visit("2026-01-01", {"left": 13.5, "right": 22.0}, 22.0)
    c = ps.compare_visits(prev, curr)[0]
    assert not c["change_detectable"] and c["label"] == "no change beyond measurement error"


def test_worst_site_switching_sides_is_not_mistaken_for_change(calibrated):
    """Visit 1 reports the right side (20), visit 2 the left side (24): the tooth-level number rises by 4, but
    neither side changed. Comparing side with side keeps this from looking like progression."""
    prev = _visit("2025-01-01", {"left": 23.0, "right": 20.0}, 23.0)
    curr = _visit("2026-01-01", {"left": 24.0, "right": 19.5}, 24.0)
    c = ps.compare_visits(prev, curr)[0]
    assert not c["change_detectable"]


def test_without_calibration_the_conservative_rule_applies(monkeypatch):
    monkeypatch.setattr(ps, "change_calibration", lambda: None)
    from app.ml.uncertainty import calibration

    monkeypatch.setattr(calibration, "current_q", lambda coverage=None: 18.6)
    prev = _visit("2025-01-01", {"left": 12.0, "right": 20.0}, 20.0)
    curr = _visit("2026-01-01", {"left": 12.5, "right": 27.0}, 27.0)
    c = ps.compare_visits(prev, curr)[0]
    assert c["change_rule"] == "accuracy_interval_sum" and not c["change_detectable"]


def test_failed_registration_is_still_unreliable_under_the_paired_rule(calibrated):
    prev = _visit("2025-01-01", {"left": 12.0, "right": 20.0}, 20.0)
    curr = _visit("2026-01-01", {"left": 12.0, "right": 35.0}, 35.0, align=0.2)
    curr["alignment"]["status"] = "failed"
    c = ps.compare_visits(prev, curr)[0]
    assert not c["reliable"] and c["label"] == "unreliable comparison"


def test_unsigned_calibration_file_is_refused(tmp_path, monkeypatch):
    from app import config

    (tmp_path / "progression_calibration.json").write_text('{"change_threshold_points": 0.1}')
    monkeypatch.setattr(config, "WEIGHTS_DIR", tmp_path)
    ps._change_cache.clear()
    assert ps.change_calibration() is None          # not in a signed manifest -> conservative rule


def test_consistent_readings_use_the_lower_threshold(monkeypatch):
    monkeypatch.setattr(ps, "change_calibration", lambda: {"change_threshold_points": 6.0, "adaptive": {
        "split_disagreement_points": 3.0, "threshold_low": 4.0, "threshold_high": 6.0}})
    prev = _visit("2025-01-01", {"left": 12.0, "right": 20.0}, 20.0)
    curr = _visit("2026-01-01", {"left": 12.0, "right": 25.0}, 25.0)          # +5 at the right side
    for t, dis in ((prev, 1.0), (curr, 2.0)):
        t["teeth"][0]["tta_disagreement_pct"] = dis
    assert ps.compare_visits(prev, curr)[0]["change_detectable"]              # 5 > 4 (consistent readings)
    curr["teeth"][0]["tta_disagreement_pct"] = 8.0
    assert not ps.compare_visits(prev, curr)[0]["change_detectable"]          # 5 < 6 (one reading inconsistent)
    curr["teeth"][0]["tta_disagreement_pct"] = None
    assert not ps.compare_visits(prev, curr)[0]["change_detectable"]          # unknown -> conservative
