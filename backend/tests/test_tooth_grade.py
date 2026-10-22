"""Panoramic per-tooth grades: the conformal set keeps every grade whose own threshold it passes, and nothing is
shown when the model is unavailable."""
import numpy as np
import pytest
import torch

from app.ml.panoramic import tooth_grade


class _Fixed(torch.nn.Module):
    """Returns the same logits for every crop."""

    def __init__(self, logits):
        super().__init__()
        self.register_buffer("logits", torch.tensor([logits], dtype=torch.float32))

    def forward(self, x):
        return self.logits.expand(x.shape[0], -1)


METRICS = {
    "grades": tooth_grade.GRADES, "input_size": 96, "crop_margin": 0.0, "conformal_target_coverage": 0.9,
    "conformal_threshold_by_grade": {"healthy": 0.5, "mild": 0.5, "medium": 0.9, "severe": 0.95},
}


def _grader(monkeypatch, logits):
    grader = tooth_grade.ToothGrader()
    monkeypatch.setattr(grader, "_load", lambda: (_Fixed(logits), METRICS))
    return grader


def test_set_keeps_each_grade_within_its_own_threshold(monkeypatch):
    # uniform logits -> p = 0.25 each -> score 0.75 per grade; only grades with threshold >= 0.75 stay
    grader = _grader(monkeypatch, [0.0, 0.0, 0.0, 0.0])
    det = [{"tooth_id": "11", "bbox": [0, 0, 40, 60]}]
    out = grader.grade_teeth(np.full((100, 100), 128, dtype=np.uint8), det)
    assert out["11"]["set"] == ["medium", "severe"]
    assert out["11"]["target_coverage"] == 0.9


def test_single_grade_when_the_model_is_confident(monkeypatch):
    grader = _grader(monkeypatch, [8.0, 0.0, 0.0, 0.0])  # healthy p ~ 0.99 -> score 0.01 <= 0.5
    out = grader.grade_teeth(np.full((100, 100), 128, dtype=np.uint8), [{"tooth_id": "12", "bbox": [0, 0, 40, 60]}])
    assert out["12"]["grade"] == "healthy"
    assert out["12"]["set"] == ["healthy"]


def test_no_grades_without_a_verified_model(monkeypatch):
    grader = tooth_grade.ToothGrader()
    monkeypatch.setattr(grader, "_load", lambda: (None, None))
    assert grader.grade_teeth(np.zeros((50, 50), np.uint8), [{"tooth_id": "11", "bbox": [0, 0, 20, 20]}]) == {}
    assert grader.available is False
