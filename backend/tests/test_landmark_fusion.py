"""Fusing keypoint readings: mirrored pass and ensemble members average per tooth; disagreement = range of readings."""
import numpy as np
import pytest

from app.ml.landmarks import fusion


def _tooth(dx=0.0, crest_y=40.0, conf=0.9):
    # cej_left, crest_left, cej_right, crest_right, apex (x, y, conf); one tooth box
    k = np.array([[10 + dx, 0, conf], [10 + dx, 20, conf], [30 + dx, 0, conf], [30 + dx, crest_y, conf],
                  [20 + dx, 100, conf]], float)
    return np.array([[0 + dx, 0, 40 + dx, 110]], float), k[None], np.array([0.9])


def test_single_reading_passes_through_with_unknown_disagreement():
    out = fusion.fuse([_tooth()])
    assert len(out) == 1 and out[0][3] is None
    assert np.allclose(out[0][1], _tooth()[1][0])


def test_two_readings_average_and_report_their_range():
    a, b = _tooth(crest_y=40.0), _tooth(crest_y=50.0)
    out = fusion.fuse([a, b])
    assert out[0][1][3, 1] == pytest.approx(45.0)                    # crest y averaged
    pa, pb = fusion.reading_pct(a[1][0]), fusion.reading_pct(b[1][0])
    assert out[0][3] == pytest.approx(abs(pa - pb))                   # = |normal - mirrored| for two readings


def test_ensemble_range_covers_all_members():
    readings = [_tooth(crest_y=y) for y in (40.0, 44.0, 52.0)]
    pcts = [fusion.reading_pct(r[1][0]) for r in readings]
    assert fusion.fuse(readings)[0][3] == pytest.approx(max(pcts) - min(pcts))


def test_a_reading_that_misses_the_tooth_does_not_contribute():
    far = (np.array([[500, 500, 540, 610]], float), _tooth()[1], np.array([0.9]))
    out = fusion.fuse([_tooth(), far])
    assert out[0][3] is None and np.allclose(out[0][1], _tooth()[1][0])


def test_unmirror_restores_coordinates_and_swaps_sides():
    boxes, kpts, _ = _tooth()
    w = 200
    mb = np.stack([w - boxes[:, 2], boxes[:, 1], w - boxes[:, 0], boxes[:, 3]], 1)
    mk = kpts.copy()
    mk[:, :, 0] = w - mk[:, :, 0]
    mk = mk[:, fusion.SWAP5]                                         # what the model reports on the mirrored film
    b2, k2 = fusion.unmirror(mb, mk, w)
    assert np.allclose(b2, boxes) and np.allclose(k2, kpts)
