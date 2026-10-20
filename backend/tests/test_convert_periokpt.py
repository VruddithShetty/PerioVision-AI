"""perio-KPT conversion: the worst of the mesial / distal sites becomes the PerioVision reference label."""
import json
import os
import subprocess
import sys

import cv2
import numpy as np

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "convert_periokpt.py")


def test_worst_site_is_written_in_periovision_order(tmp_path):
    w, h = 400, 600
    (tmp_path / "img").mkdir(); (tmp_path / "lab").mkdir()
    cv2.imwrite(str(tmp_path / "img" / "a.png"), np.full((h, w), 90, np.uint8))
    # one Single Root tooth: CEJ-m (150,100) BL-m (150,250 -> deep), RL-m (180,550), CEJ-d (250,100) BL-d (250,130),
    # RL-d (220,550), RL-c (200,560); FA, FBL-m, FBL-d, ARR not visible
    pts = [(150, 100, 2), (150, 250, 2), (180, 550, 2), (250, 100, 2), (250, 130, 2), (220, 550, 2), (200, 560, 2),
           (0, 0, 0), (0, 0, 0), (0, 0, 0), (0, 0, 0)]
    vals = [0, 200 / w, 330 / h, 160 / w, 520 / h] + [c for x, y, v in pts for c in (x / w, y / h, v)]
    (tmp_path / "lab" / "a.txt").write_text(" ".join(map(str, vals)) + "\n")
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, SCRIPT, "--images", str(tmp_path / "img"), "--labels", str(tmp_path / "lab"),
                        "--out", str(out), "--check-images", "1"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    v = list(map(float, (out / "labels" / "a.txt").read_text().split()))
    cej, apex, crest = (np.array([v[5 + 3 * i] * w, v[6 + 3 * i] * h]) for i in range(3))
    assert np.allclose(cej, (150, 100), atol=0.1) and np.allclose(crest, (150, 250), atol=0.1)   # mesial = worst
    assert np.allclose(apex, (200, 553.33), atol=0.1)                                           # mean of root limits
    assert json.loads((out / "conversion_report.json").read_text())["keypoint_order_plausible"]
