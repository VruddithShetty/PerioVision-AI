"""Two-site (5-keypoint) bone-loss logic: worst confident site, and mirror symmetry of the left/right swap."""
import numpy as np
import pytest

from research.compare_landmark_models import SWAP5, pct, tooth_pct


def _tooth():
    # cej_left, crest_left, cej_right, crest_right, apex  (x, y, conf); root axis points down
    return np.array([[10, 0, .9], [10, 20, .9], [30, 0, .9], [30, 40, .9], [20, 100, .9]], float)


def test_worst_confident_site_is_reported():
    k = _tooth()
    left, right = pct(k[0, :2], k[4, :2], k[1, :2]), pct(k[2, :2], k[4, :2], k[3, :2])
    assert right > left
    assert tooth_pct(k, 5, 0.5) == pytest.approx(right)
    k[3, 2] = 0.2                                   # right crest not confident -> only the left site counts
    assert tooth_pct(k, 5, 0.5) == pytest.approx(left)
    k[1, 2] = 0.2
    assert tooth_pct(k, 5, 0.5) is None             # no confident site -> not measured, never a default


def test_mirror_then_swap_gives_the_same_bone_loss():
    k, w = _tooth(), 200.0
    m = k.copy()
    m[:, 0] = w - m[:, 0]                          # what the model sees on the mirrored film ...
    m = m[SWAP5]                                    # ... its "left" site is our right site
    back = m[SWAP5].copy()
    back[:, 0] = w - back[:, 0]
    assert np.allclose(back, k)
    assert tooth_pct(m, 5, 0.5) == pytest.approx(tooth_pct(k, 5, 0.5))


def test_pct_matches_the_app_formula():
    from app.ml.measurement.bone_loss import bone_loss_for_tooth

    k = _tooth()
    app = bone_loss_for_tooth({"cej": k[2, :2], "root_apex": k[4, :2], "bone_crest": k[3, :2]})["bone_loss_pct"]
    assert pct(k[2, :2], k[4, :2], k[3, :2]) == pytest.approx(app, abs=0.01)
