# TALPA — Temporal Analysis of Longitudinal Periodontal Attachment

> **Status:** Active implementation. See `src/analysis/progression_velocity_calculator.py` for the core engine.

## Overview

TALPA is the AI-powered grading engine inside PerioVision AI. It replaces point-in-time bone loss severity scores with a **temporal velocity vector** — the rate of bone loss in mm/year per tooth site — and classifies each site against the **2017 AAP/EFP World Workshop** periodontal staging and grading criteria.

---

## Clinical Basis

### The 2017 AAP/EFP Grading System
> Tonetti MS et al. *J Clin Periodontol.* 2018;45 Suppl 20:S149–S161

The 2017 classification introduced a **Grading axis** (A/B/C) that is orthogonal to Stage (I–IV, reflecting cumulative severity). Grade specifically measures the **rate** of disease progression, making it the ideal metric for longitudinal radiographic tracking.

| Grade | Description | Primary Criterion (Radiographic Bone Loss Rate) |
|-------|-------------|--------------------------------------------------|
| A | Slow / No Progression | < 0.25 mm/year |
| B | Moderate Progression | 0.25 – 1.0 mm/year |
| C | Rapid Progression | > 1.0 mm/year |

### Risk Factor Escalators
Risk factors can **escalate** a grade (B→C) but **cannot de-escalate** it. The following are checked in order after the primary velocity-based grade is assigned:

| Risk Factor | Threshold | Effect |
|-------------|-----------|--------|
| Smoking | ≥ 10 cigarettes/day | B → C |
| Glycaemic control | HbA1c ≥ 7.0% | B → C |
| Vertical bone loss | ≥ 3.0 mm | B → C |
| Furcation involvement | Class II or III | B → C |

### CEJ/ABC Landmark Measurement
The alveolar bone crest (ABC) migrates apically away from the cemento-enamel junction (CEJ) as bone is lost. TALPA measures the CEJ-to-ABC distance in millimetres from geometrically-aligned serial radiographs. An **increase** in this distance over time = bone loss.

```
Normal baseline: ~2.0 mm (CEJ to ABC)
Active bone loss: CEJ-to-ABC > 3.0 mm
```

---

## Novel System Contribution (Patent Notes)

Prior art systems (CADIAX, Planmeca Romexis, Vatech Ez3D) produce only **point-in-time severity scores**. TALPA's patentable novelty is threefold:

1. **Velocity Vectors per Site**: Integrates geometrically-aligned CEJ/ABC coordinates from serial radiographs with patient visit timestamps to produce a per-tooth-site velocity in mm/year, not just a static measurement.

2. **Per-Tooth Grade Trajectory**: For teeth with 3+ radiograph timepoints, TALPA compares the grade assigned to the earliest observation window against the latest and classifies the change as `ESCALATED`, `STABILISED`, or `IMPROVED`. No prior art system tracks longitudinal grade change at the per-site level.

3. **Prospective Escalation Risk (12/24-Month Horizon)**: Using the current velocity trajectory (linear extrapolation), TALPA projects whether a Grade B site will cross the Grade C threshold within 12 or 24 months. This is a prospective, predictive capability — not retrospective severity scoring.

---

## API Schemas

### `calculate_velocity()` Input (per measurement)

```json
{
  "date":                 "YYYY-MM-DD",
  "tooth_id":             11,
  "site":                 "mesial | distal | buccal | lingual",
  "cej_to_abc_mm":        2.4,
  "alignment_confidence": 0.85
}
```

### `calculate_velocity()` Output

```json
{
  "tooth_id":               11,
  "site":                   "mesial",
  "velocity_mm_per_year":   0.42,
  "bone_loss_delta_mm":     0.84,
  "time_span_years":        2.0,
  "low_confidence_velocity": false,
  "uncertainty_margin_mm":  0.0,
  "measurement_count":      2,
  "date_range":             { "first": "2023-01-01", "last": "2025-01-01" },
  "insufficient_data":      false
}
```

If fewer than 2 timepoints are available, or the time span is < 6 months:

```json
{
  "insufficient_data": true,
  "reason":            "Time span 0.23 years is below the minimum 0.5 year threshold."
}
```

### `classify_aap_efp_grade()` Output

```json
{
  "grade":                    "B",
  "grade_label":              "Grade B – Moderate Progression",
  "primary_criterion":        "velocity 0.420 mm/year is 0.25–1.0 (Grade B)",
  "modifier_applied":         null,
  "escalated_by_risk_factor": false,
  "clinical_recommendation":  "Schedule supportive periodontal therapy every 6 months..."
}
```

### `compute_full_mouth_velocity_profile()` Output

```json
{
  "per_site_results": [ ... ],
  "full_mouth_summary": {
    "overall_grade":           "C",
    "grade_distribution":      { "A": 4, "B": 10, "C": 2, "None": 1 },
    "highest_velocity_site":   { "tooth_id": 36, "site": "mesial", "velocity_mm_per_year": 1.8 },
    "teeth_requiring_attention": [36, 46],
    "per_tooth_grade_trajectory": {
      "36_mesial": { "early_grade": "B", "late_grade": "C", "trajectory": "ESCALATED" }
    }
  },
  "computed_at":        "2025-05-05T07:15:00Z",
  "low_confidence_sites": 1
}
```

### `estimate_future_grade_risk()` Output

```json
{
  "escalation_risk_profile": [
    {
      "tooth_id":                    21,
      "site":                        "mesial",
      "current_grade":               "B",
      "current_velocity_mm_per_year": 0.8,
      "at_risk_12_months":           false,
      "at_risk_24_months":           true,
      "projected_velocity_12m":      0.8,
      "projected_velocity_24m":      1.6
    }
  ],
  "high_risk_tooth_count": 1
}
```

---

## Landmark Interface Contract

The `RadiographAligner` is expected to emit the following structure once fully implemented. Until then, a proxy conversion (`bone_loss_pct / 10 + 2.0 mm`) is used.

```python
# TODO: Wire this once RadiographAligner implements full landmark extraction.
landmark_coordinates = {
    tooth_id (int, FDI notation): {
        site (str): {
            "cej_xy":             [float, float],   # pixel coords in aligned image
            "abc_xy":             [float, float],   # alveolar bone crest pixel coords
            "cej_to_abc_mm":      float,            # calibrated distance in mm
            "alignment_confidence": float           # 0.0 – 1.0 from RadiographAligner
        }
    }
}
```

The `build_longitudinal_landmark_dict()` function in `server.py` will merge this with historical database records once the aligner is upgraded.

---

## Pipeline Stages (`/api/analyze`)

| Stage | Description |
|-------|-------------|
| 1 | Preprocessing (normalisation, CLAHE) |
| 2 | Tooth detection (YOLO) + bone loss calculation |
| 3 | Landmark data assembly (`build_longitudinal_landmark_dict`) |
| 4 | TALPA velocity & grade computation (`ProgressionVelocityCalculator`) |
| 5 | Future escalation risk (`estimate_future_grade_risk`) |
| 6 | Clinical annotation overlay (`draw_findings_on_image`) |
| 7 | Database persistence + JSON response |

---

## Running the Unit Tests

```bash
cd dental_progression_ai
python -m pytest tests/test_progression_velocity_calculator.py -v
```

The test suite covers:
- Grade A/B/C primary velocity assignment
- All four risk factor escalation paths (smoking, HbA1c, VBL, furcation)
- 6-month minimum time span enforcement
- Low-confidence alignment uncertainty bounds
- 12/24-month future escalation risk projection

---

## Key Design Decisions

### Why `bone_loss_pct / 10` as a proxy for `cej_to_abc_mm`?
Until the `RadiographAligner` implements full CEJ/ABC pixel detection and mm calibration, we approximate: `2.0 mm (normal) + (bone_loss_pct / 10)`. This gives a rough linear relationship between the percentage-based legacy score and a physical distance. It is explicitly flagged as a proxy in code and this document; replace with true mm values once landmark extraction is wired.

### Why is `MIN_TIME_SPAN_YEARS = 0.5`?
Short observation windows yield unreliable velocity estimates. The 2017 AAP/EFP framework implicitly requires ≥ 5 years for definitive Grade C direct evidence. Six months is the minimum meaningful interval for interim monitoring. Spans shorter than this return `insufficient_data` rather than extrapolating.

### Why can risk factors only escalate, never de-escalate?
This directly follows Tonetti et al. 2018. The grade represents the patient's worst-case disease trajectory. A well-controlled diabetic with Grade C velocity is still Grade C — good HbA1c reduces future risk but does not retroactively improve the historical record.
