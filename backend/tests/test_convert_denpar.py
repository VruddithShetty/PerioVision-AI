"""DenPAR label conversion: the crest must come from the same side of the tooth as the CEJ.

Regression test for the 2026-10-06 fix: with a single annotated CEJ the converter used to accept a bone-line point
from either side of the tooth, which paired the CEJ of one side with the crest of the other on 10-14 % of teeth.
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import convert_denpar  # noqa: E402
import convert_denpar_twosite  # noqa: E402


def _tooth_mask():
    m = np.zeros((400, 300), bool)
    m[50:380, 100:200] = True            # tooth from x 100 to 200, centre x = 150
    return m


def _case():
    kp = {"CEJ_Points": [[195.0, 120.0]],                 # one CEJ, on the RIGHT side
          "Apex_Points": [[150.0, 375.0]]}
    bone = {"Bone_Lines": [[[105.0, 300.0], [102.0, 310.0]],    # deep bone on the LEFT side (would look worst)
                           [[196.0, 160.0], [198.0, 165.0]]]}   # shallow bone on the right side
    return kp, bone


def test_single_cej_takes_the_crest_from_its_own_side():
    kp, bone = _case()
    rows = convert_denpar.convert_image(kp, bone, [_tooth_mask()])
    assert len(rows) == 1
    assert rows[0]["crest"][0] > 150, "crest was taken from the opposite side of the tooth"


def test_two_site_converter_uses_the_same_rule():
    kp, bone = _case()
    rows = convert_denpar_twosite.convert_image(kp, bone, [_tooth_mask()])
    sites = rows[0]["sites"]
    assert sites["left"] is None
    assert sites["right"]["crest"][0] > 150


def test_two_cej_points_keep_their_own_sides():
    kp = {"CEJ_Points": [[105.0, 120.0], [195.0, 120.0]], "Apex_Points": [[150.0, 375.0]]}
    _, bone = _case()
    rows = convert_denpar_twosite.convert_image(kp, bone, [_tooth_mask()])
    s = rows[0]["sites"]
    assert s["left"]["crest"][0] < 150 and s["right"]["crest"][0] > 150
    assert s["left"]["ratio"] > s["right"]["ratio"]          # the deep left site is the worst site
