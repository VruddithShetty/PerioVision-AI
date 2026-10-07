"""Quality gate: smooth but valid periapical films pass (with a warning); heavily blurred films are refused."""
import cv2
import numpy as np

from app.ml.preprocessing.quality_check import assess_quality


def _film(seed=0):
    rng = np.random.default_rng(seed)
    img = np.full((1100, 800), 60, np.uint8)
    for x in (120, 360, 600):                                   # three tooth-like columns with texture
        cv2.rectangle(img, (x, 150), (x + 140, 1000), 175, -1)
    img = cv2.add(img, rng.integers(0, 30, img.shape).astype(np.uint8))
    return img


def _sharpness(img):
    return assess_quality(img)["metrics"]["sharpness"]


def test_a_smooth_valid_periapical_film_is_not_refused():
    soft = cv2.GaussianBlur(_film(), (0, 0), 1.4)               # smooth like the softest real DenPAR films
    q = assess_quality(soft)
    assert 3.0 <= _sharpness(soft) < 25.0, _sharpness(soft)
    assert q["verdict"] != "reject" and any("blurry" in r["message"] for r in q["reasons"])   # warned, not refused


def test_a_heavily_blurred_film_is_still_refused():
    blurred = cv2.GaussianBlur(_film(), (0, 0), 12)
    q = assess_quality(blurred)
    assert q["verdict"] == "reject" and any("too blurry" in r["message"] for r in q["reasons"])
