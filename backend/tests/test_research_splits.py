"""Patient-level splitting and the leakage audit behave as documented."""
import cv2
import numpy as np
import pytest

from research import split_audit


def _rows(n_patients=60, imgs_per_patient=3):
    return [{"image": f"p{p}_{i}.png", "patient_id": f"P{p}", "stratum": str(p % 3)}
            for p in range(n_patients) for i in range(imgs_per_patient)]


def test_make_split_never_puts_a_patient_in_two_splits():
    rows = _rows()
    split = split_audit.make_split(rows, seed=3)
    owner = {}
    for name, imgs in split.items():
        for img in imgs:
            pid = img.split("_")[0]
            assert owner.setdefault(pid, name) == name
    assert sum(len(v) for v in split.values()) == len(rows)
    assert 0.6 < len(split["train"]) / len(rows) < 0.8


def test_verify_split_catches_a_leak():
    rows = _rows(4, 2)
    patient_of = {r["image"]: r["patient_id"] for r in rows}
    leaky = {"train": ["p0_0.png"], "val": [], "test": ["p0_1.png"]}
    with pytest.raises(AssertionError):
        split_audit.verify_split(leaky, patient_of)


def test_make_split_requires_patient_ids():
    with pytest.raises(SystemExit):
        split_audit.make_split([{"image": "a.png", "patient_id": None}])


def test_audit_finds_a_copied_film_across_splits(tmp_path):
    rng = np.random.default_rng(0)
    films = [cv2.GaussianBlur(rng.integers(0, 255, (200, 400), dtype=np.uint8), (31, 31), 0) for _ in range(4)]
    rows = []
    for i, f in enumerate(films):
        p = tmp_path / f"f{i}.png"
        cv2.imwrite(str(p), f)
        rows.append({"image": str(p), "split": "train", "patient_id": None})
    copy = tmp_path / "copy.jpg"                       # same film, re-saved as JPEG, in the test split
    cv2.imwrite(str(copy), films[2], [cv2.IMWRITE_JPEG_QUALITY, 85])
    rows.append({"image": str(copy), "split": "test", "patient_id": None})
    rep = split_audit.audit(rows, None, max_hamming=4)
    assert rep["near_duplicates_confirmed_across_splits"] == 1
    assert rep["check_duplicates"].startswith("FAIL")
