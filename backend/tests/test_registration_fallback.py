"""Registration accepts a re-take with a slight beam tilt (affine fallback) and still refuses unrelated images."""
import cv2
import numpy as np

from app.ml.preprocessing.alignment import RadiographAligner


def _film(seed):
    rng = np.random.default_rng(seed)
    img = cv2.GaussianBlur(rng.integers(0, 255, (700, 1000)).astype(np.uint8), (0, 0), 3)
    for i in range(6):                                    # tooth-like bright columns with texture
        cv2.rectangle(img, (80 + 150 * i, 120), (170 + 150 * i, 600), int(150 + 15 * i), -1)
    return cv2.addWeighted(img, 0.7, cv2.GaussianBlur(rng.integers(0, 255, img.shape).astype(np.uint8), (0, 0), 1), 0.3, 0)


def _stretched(img, sx, sy, shear):
    """A re-take at a slightly different beam angle: small anisotropic stretch and shear."""
    h, w = img.shape
    return cv2.warpAffine(img, np.float32([[sx, shear, -20], [0.0, sy, 15]]), (w, h), borderMode=cv2.BORDER_REFLECT)


def test_affine_fallback_registers_a_slightly_sheared_retake():
    film, moved = _film(1), _stretched(_film(1), 1.06, 0.96, 0.03)
    old = RadiographAligner()
    old.AFFINE_FALLBACK = False
    old.align_by_features(film, moved)
    assert old.last_alignment_info["alignment_status"] == "failed"          # rotation + scale alone cannot fit it
    new = RadiographAligner()
    new.align_by_features(film, moved)
    info = new.last_alignment_info
    assert info["alignment_status"] == "success" and info["transform"] == "affine", info


def test_implausible_stretch_is_refused_even_with_the_fallback():
    a = RadiographAligner()
    a.align_by_features(_film(1), _stretched(_film(1), 1.10, 0.95, 0.05))
    assert a.last_alignment_info["alignment_status"] == "failed"
    assert "shear" in a.last_alignment_info["reason"]


def test_unrelated_images_are_still_refused():
    a = RadiographAligner()
    a.align_by_features(_film(1), _film(2))
    assert a.last_alignment_info["alignment_status"] == "failed"
