import datetime
import logging
from typing import Optional

logger = logging.getLogger("TALPA.ProgressionVelocityCalculator")

# TODO: Replace with RadiographAligner output once landmark_coordinates are implemented.
# See docs/TALPA.md for the full interface contract schema.
LANDMARK_COORDINATE_SCHEMA = {}

# 2017 AAP/EFP thresholds — see docs/TALPA.md for grading criteria details.
GRADE_A_MAX_VELOCITY_MM_YR = 0.25
GRADE_B_MAX_VELOCITY_MM_YR = 1.0

CLINICAL_RECOMMENDATIONS = {
    "A": "Continue annual supportive periodontal therapy (SPT). "
         "Monitor radiographically every 24 months.",
    "B": "Schedule supportive periodontal therapy every 6 months. "
         "Repeat radiographic measurement at 12 months.",
    "C": "Consider 3-monthly supportive periodontal therapy (SPT). "
         "Urgent risk factor modification. Specialist referral recommended.",
}

LOW_CONFIDENCE_THRESHOLD = 0.6
MIN_TIME_SPAN_YEARS = 0.5


class ProgressionVelocityCalculator:
    """
    Computes temporal bone loss velocity (mm/year) and assigns 2017 AAP/EFP
    progression grades (A/B/C) from serial CEJ/ABC landmark measurements.

    See docs/TALPA.md for full clinical methodology, API schemas, and patent notes.
    """

    def calculate_velocity(self, measurements: list) -> dict:
        """
        Compute CEJ-to-ABC bone loss velocity in mm/year from timestamped measurements.

        Returns insufficient_data=True if fewer than 2 points exist or the
        time span is under 6 months. Sets low_confidence_velocity=True and
        adds a ±15% uncertainty margin if any alignment_confidence < 0.6.

        Input schema per measurement:
            date (str YYYY-MM-DD), tooth_id (int), site (str),
            cej_to_abc_mm (float), alignment_confidence (float 0–1)

        See docs/TALPA.md for full output schema.
        """
        # Exclude heuristic fallback measurements
        measurements = [m for m in measurements if m.get("confidence_source") != "heuristic_fallback"]
        if not measurements or len(measurements) < 2:
            return {
                "tooth_id": measurements[0].get("tooth_id") if measurements else None,
                "site": measurements[0].get("site") if measurements else None,
                "insufficient_data": True,
                "reason": "Fewer than 2 measurement timepoints available.",
                "measurement_count": len(measurements),
                "velocity_mm_per_year": None,
                "bone_loss_delta_mm": None,
                "time_span_years": None,
            }

        def parse_date(m):
            return datetime.date.fromisoformat(m["date"])

        sorted_meas = sorted(measurements, key=parse_date)
        first = sorted_meas[0]
        last = sorted_meas[-1]

        date_first = parse_date(first)
        date_last = parse_date(last)
        time_span_years = (date_last - date_first).days / 365.25

        tooth_id = first.get("tooth_id")
        site = first.get("site")

        # Check measurement type homogeneity
        if first.get("measurement_type") != last.get("measurement_type"):
            return {
                "tooth_id": tooth_id,
                "site": site,
                "insufficient_data": True,
                "reason": f"Mismatch in measurement types: first is {first.get('measurement_type')}, last is {last.get('measurement_type')}",
                "measurement_count": len(measurements),
                "velocity_mm_per_year": None,
                "bone_loss_delta_mm": None,
                "time_span_years": round(time_span_years, 3),
                "date_range": {"first": first["date"], "last": last["date"]},
            }

        # Check alignment confidence gate
        if any(m.get("alignment_status") == "failed" for m in sorted_meas):
            return {
                "tooth_id": tooth_id,
                "site": site,
                "insufficient_data": True,
                "reason": "Alignment failed.",
                "measurement_count": len(measurements),
                "velocity_mm_per_year": None,
                "bone_loss_delta_mm": None,
                "time_span_years": round(time_span_years, 3),
                "date_range": {"first": first["date"], "last": last["date"]},
                "alignment_status": "failed"
            }

        if time_span_years < MIN_TIME_SPAN_YEARS:
            return {
                "tooth_id": tooth_id,
                "site": site,
                "insufficient_data": True,
                "reason": f"Time span {time_span_years:.2f} years is below the "
                          f"minimum {MIN_TIME_SPAN_YEARS} year threshold.",
                "measurement_count": len(measurements),
                "velocity_mm_per_year": None,
                "bone_loss_delta_mm": None,
                "time_span_years": round(time_span_years, 3),
                "date_range": {"first": first["date"], "last": last["date"]},
            }

        # Standard Error Propagation: uncertainty = sqrt(err1^2 + err2^2)
        c1 = first.get("landmark_confidence", 0.85)
        c2 = last.get("landmark_confidence", 0.85)
        err1 = 0.5 * (1.0 - c1) + 0.2
        err2 = 0.5 * (1.0 - c2) + 0.2
        import math
        measurement_uncertainty_mm = math.sqrt(err1**2 + err2**2)

        bone_loss_delta_mm = last["cej_to_abc_mm"] - first["cej_to_abc_mm"]

        # Category 2: Robust Theil-Sen Estimator for >= 3 visits vs 2-point delta
        max_gap_found_years = 0.0
        for idx in range(1, len(sorted_meas)):
            gap_days = (parse_date(sorted_meas[idx]) - parse_date(sorted_meas[idx-1])).days
            gap_yrs = gap_days / 365.25
            if gap_yrs > max_gap_found_years:
                max_gap_found_years = gap_yrs

        gap_warning = "long interval — trend may mask acute episodes" if max_gap_found_years > 3.0 else None

        if len(sorted_meas) >= 3:
            import numpy as np
            slopes = []
            dates_years = [(parse_date(m) - date_first).days / 365.25 for m in sorted_meas]
            vals = [m["cej_to_abc_mm"] for m in sorted_meas]
            for i in range(len(sorted_meas)):
                for j in range(i + 1, len(sorted_meas)):
                    dt = dates_years[j] - dates_years[i]
                    if dt > 0:
                        slopes.append((vals[j] - vals[i]) / dt)
            if slopes:
                velocity_mm_per_year = float(np.median(slopes))
            else:
                velocity_mm_per_year = bone_loss_delta_mm / time_span_years
            trend_method = "theil_sen"
        else:
            velocity_mm_per_year = bone_loss_delta_mm / time_span_years
            trend_method = "two_point_delta"

        # Hard Rule: If abs(delta_mm) < uncertainty_mm, report as within_measurement_noise
        if abs(bone_loss_delta_mm) < measurement_uncertainty_mm:
            progression_status = "within_measurement_noise"
        elif bone_loss_delta_mm > 0:
            progression_status = "progressive_loss"
        else:
            progression_status = "stable_or_repaired"

        low_confidence = any(
            m.get("alignment_confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD
            for m in sorted_meas
        )
        uncertainty_margin_mm = abs(velocity_mm_per_year) * 0.15 if low_confidence else 0.0

        if low_confidence:
            logger.warning(
                f"Tooth {tooth_id} site {site}: alignment_confidence < "
                f"{LOW_CONFIDENCE_THRESHOLD}. Velocity has ±15% uncertainty margin."
            )

        landmark_sources = list(set(m.get("landmark_source", m.get("confidence_source", "trained_keypoint_model")) for m in sorted_meas))
        landmark_source_summary = landmark_sources[0] if len(landmark_sources) == 1 else "mixed"

        return {
            "tooth_id": tooth_id,
            "site": site,
            "velocity_mm_per_year": round(velocity_mm_per_year, 4),
            "bone_loss_delta_mm": round(bone_loss_delta_mm, 4),
            "time_span_years": round(time_span_years, 3),
            "measurement_uncertainty_mm": round(measurement_uncertainty_mm, 4),
            "progression_status": progression_status,
            "landmark_source": landmark_source_summary,
            "trend_method": trend_method,
            "max_interval_gap_years": round(max_gap_found_years, 3),
            "gap_warning": gap_warning,
            "low_confidence_velocity": low_confidence,
            "uncertainty_margin_mm": round(uncertainty_margin_mm, 4),
            "measurement_count": len(measurements),
            "date_range": {"first": first["date"], "last": last["date"]},
            "insufficient_data": False,
        }

    def classify_aap_efp_grade(
        self,
        velocity_mm_per_year: float,
        time_span_years: float,
        risk_factors: Optional[dict] = None,
    ) -> dict:
        """
        Assign an AAP/EFP 2017 progression grade (A/B/C) from velocity + risk factors.

        Primary thresholds: A < 0.25, B 0.25–1.0, C > 1.0 mm/year.
        Risk factors can escalate the grade but never de-escalate it.
        Accepted risk_factors keys: smoker_cpd, hba1c, vertical_bone_loss_mm, furcation_class.

        See docs/TALPA.md for full criteria, escalation rules, and clinical basis.
        """
        rf = risk_factors or {}

        if velocity_mm_per_year < GRADE_A_MAX_VELOCITY_MM_YR:
            grade = "A"
            primary_criterion = f"velocity {velocity_mm_per_year:.3f} mm/year < 0.25 (Grade A)"
        elif velocity_mm_per_year <= GRADE_B_MAX_VELOCITY_MM_YR:
            grade = "B"
            primary_criterion = f"velocity {velocity_mm_per_year:.3f} mm/year is 0.25–1.0 (Grade B)"
        else:
            grade = "C"
            primary_criterion = f"velocity {velocity_mm_per_year:.3f} mm/year > 1.0 (Grade C)"

        modifier_applied = None
        escalated_by_risk_factor = False

        if grade != "C":
            smoker_cpd = rf.get("smoker_cpd", 0)
            if smoker_cpd >= 10:
                grade = "C"
                modifier_applied = f"Heavy smoker ({smoker_cpd} CPD ≥ 10)"
                escalated_by_risk_factor = True

            if not escalated_by_risk_factor:
                hba1c = rf.get("hba1c") if rf.get("hba1c") is not None else rf.get("diabetes_hba1c")
                if hba1c is not None and hba1c >= 7.0:
                    grade = "C"
                    modifier_applied = f"HbA1c {hba1c:.1f}% ≥ 7.0%"
                    escalated_by_risk_factor = True

            if not escalated_by_risk_factor:
                vbl = rf.get("vertical_bone_loss_mm", 0.0)
                if vbl >= 3.0:
                    grade = "C"
                    modifier_applied = f"Vertical bone loss {vbl:.1f} mm ≥ 3.0 mm"
                    escalated_by_risk_factor = True

            if not escalated_by_risk_factor:
                furcation = rf.get("furcation_class", 0)
                if furcation >= 2:
                    grade = "C"
                    modifier_applied = f"Furcation Class {furcation} (II/III)"
                    escalated_by_risk_factor = True

        grade_labels = {
            "A": "Grade A – Slow/No Progression",
            "B": "Grade B – Moderate Progression",
            "C": "Grade C – Rapid Progression",
        }

        return {
            "grade": grade,
            "grade_label": grade_labels[grade],
            "primary_criterion": primary_criterion,
            "modifier_applied": modifier_applied,
            "escalated_by_risk_factor": escalated_by_risk_factor,
            "clinical_recommendation": CLINICAL_RECOMMENDATIONS[grade],
        }

    def compute_full_mouth_velocity_profile(
        self,
        landmark_data: dict,
        visit_dates: dict,
        risk_factors: Optional[dict] = None,
    ) -> dict:
        """
        Top-level TALPA driver. Iterates all tooth/site pairs, computes velocity
        and grades per site, then aggregates a full-mouth summary.

        Returns overall_grade (worst across all sites), grade_distribution,
        highest_velocity_site, teeth_requiring_attention (Grade C), and the
        novel per_tooth_grade_trajectory (ESCALATED/STABILISED/IMPROVED for
        teeth with 3+ timepoints).

        See docs/TALPA.md for full output schema and clinical interpretation.
        """
        per_site_results = []
        low_confidence_site_count = 0

        for tooth_id, sites in landmark_data.items():
            for site_name, measurements_raw in sites.items():
                measurements = []
                for m in measurements_raw:
                    entry = dict(m)
                    entry.setdefault("tooth_id", tooth_id)
                    entry.setdefault("site", site_name)
                    measurements.append(entry)

                vel_result = self.calculate_velocity(measurements)

                if vel_result.get("insufficient_data"):
                    per_site_results.append({
                        "tooth_id": tooth_id,
                        "site": site_name,
                        "velocity_result": vel_result,
                        "grade_result": {
                            "grade": None,
                            "grade_label": "Insufficient Temporal Data",
                            "insufficient_temporal_data": True,
                        },
                    })
                    continue

                if vel_result.get("low_confidence_velocity"):
                    low_confidence_site_count += 1

                grade_result = self.classify_aap_efp_grade(
                    velocity_mm_per_year=vel_result["velocity_mm_per_year"],
                    time_span_years=vel_result["time_span_years"],
                    risk_factors=risk_factors,
                )

                per_site_results.append({
                    "tooth_id": tooth_id,
                    "site": site_name,
                    "velocity_result": vel_result,
                    "grade_result": grade_result,
                })

        grade_distribution = {"A": 0, "B": 0, "C": 0, "None": 0}
        graded_sites = []
        highest_velocity = None
        highest_velocity_site = None

        for sr in per_site_results:
            grade = sr["grade_result"].get("grade")
            if grade in grade_distribution:
                grade_distribution[grade] += 1
            else:
                grade_distribution["None"] += 1

            if grade is not None:
                graded_sites.append(sr)
                vel = sr["velocity_result"].get("velocity_mm_per_year")
                if vel is not None:
                    if highest_velocity is None or vel > highest_velocity:
                        highest_velocity = vel
                        highest_velocity_site = {
                            "tooth_id": sr["tooth_id"],
                            "site": sr["site"],
                            "velocity_mm_per_year": vel,
                        }

        if grade_distribution["C"] > 0:
            overall_grade = "C"
        elif grade_distribution["B"] > 0:
            overall_grade = "B"
        elif grade_distribution["A"] > 0:
            overall_grade = "A"
        else:
            overall_grade = None

        teeth_requiring_attention = list(set(
            sr["tooth_id"]
            for sr in per_site_results
            if sr["grade_result"].get("grade") == "C"
        ))

        # Novel feature: grade trajectory over time (requires 3+ timepoints).
        # See docs/TALPA.md for interpretation.
        per_tooth_grade_trajectory = {}
        for tooth_id_key, sites in landmark_data.items():
            for site_name, measurements_raw in sites.items():
                if len(measurements_raw) < 3:
                    per_tooth_grade_trajectory[f"{tooth_id_key}_{site_name}"] = {
                        "early_grade": None,
                        "late_grade": None,
                        "trajectory": "STABLE",
                        "velocity_mm_per_year": None,
                        "grade": None
                    }
                    continue
                # Ensure all measurements have tooth_id and site set
                measurements_decorated = []
                for m in measurements_raw:
                    entry = dict(m)
                    entry.setdefault("tooth_id", tooth_id_key)
                    entry.setdefault("site", site_name)
                    measurements_decorated.append(entry)
                sorted_meas = sorted(measurements_decorated, key=lambda m: m["date"])

                early_vel = self.calculate_velocity(sorted_meas[:2] + [dict(sorted_meas[0])])
                late_vel = self.calculate_velocity(sorted_meas[-2:])

                if early_vel.get("insufficient_data") or late_vel.get("insufficient_data"):
                    continue

                early_grade = self.classify_aap_efp_grade(
                    early_vel["velocity_mm_per_year"], early_vel["time_span_years"], risk_factors
                )["grade"]
                late_grade = self.classify_aap_efp_grade(
                    late_vel["velocity_mm_per_year"], late_vel["time_span_years"], risk_factors
                )["grade"]

                grade_order = {"A": 0, "B": 1, "C": 2}
                if grade_order[late_grade] > grade_order[early_grade]:
                    trajectory = "ESCALATED"
                elif grade_order[late_grade] < grade_order[early_grade]:
                    trajectory = "IMPROVED"
                else:
                    trajectory = "STABILISED"

                per_tooth_grade_trajectory[f"{tooth_id_key}_{site_name}"] = {
                    "early_grade": early_grade,
                    "late_grade": late_grade,
                    "trajectory": trajectory,
                }

        return {
            "per_site_results": per_site_results,
            "full_mouth_summary": {
                "overall_grade": overall_grade,
                "grade_distribution": grade_distribution,
                "highest_velocity_site": highest_velocity_site,
                "teeth_requiring_attention": teeth_requiring_attention,
                "per_tooth_grade_trajectory": per_tooth_grade_trajectory,
            },
            "computed_at": datetime.datetime.utcnow().isoformat() + "Z",
            "low_confidence_sites": low_confidence_site_count,
        }

    def estimate_future_grade_risk(self, per_site_results: list) -> dict:
        """
        Project whether Grade B sites will escalate to Grade C within 12 or 24 months
        assuming current velocity continues unchanged (linear extrapolation).

        Only Grade B sites are evaluated. Grade A and C sites are excluded.
        See docs/TALPA.md for full methodology and patent notes.
        """
        escalation_risk_profile = []

        for sr in per_site_results:
            grade = sr["grade_result"].get("grade")
            if grade != "B":
                continue

            velocity = sr["velocity_result"].get("velocity_mm_per_year", 0.0)
            projected_12m = velocity * 1.0
            projected_24m = velocity * 2.0
            at_risk_12m = projected_12m > GRADE_B_MAX_VELOCITY_MM_YR
            at_risk_24m = projected_24m > GRADE_B_MAX_VELOCITY_MM_YR

            escalation_risk_profile.append({
                "tooth_id": sr["tooth_id"],
                "site": sr["site"],
                "current_grade": "B",
                "current_velocity_mm_per_year": velocity,
                "at_risk_12_months": at_risk_12m,
                "at_risk_24_months": at_risk_24m,
                "projected_velocity_12m": round(projected_12m, 4),
                "projected_velocity_24m": round(projected_24m, 4),
            })

        high_risk_count = sum(
            1 for r in escalation_risk_profile
            if r["at_risk_12_months"] or r["at_risk_24_months"]
        )

        return {
            "escalation_risk_profile": escalation_risk_profile,
            "high_risk_tooth_count": high_risk_count,
        }

    def _get_val(self, item: dict) -> float:
        if "bone_loss_percentage" in item:
            return float(item["bone_loss_percentage"])
        elif "cej_to_abc_mm" in item:
            return float(item["cej_to_abc_mm"])
        else:
            raise ValueError("Each time series point must have bone_loss_percentage or cej_to_abc_mm")

    def _get_date(self, item: dict) -> str:
        if "date" in item:
            return str(item["date"])
        elif "radiograph_date" in item:
            return str(item["radiograph_date"])
        else:
            raise KeyError("Time series point must contain 'date' or 'radiograph_date'")

    def compute_progression_velocity(self, time_series: list) -> dict:
        """
        Compute progression velocity between the two most recent time points.
        """
        time_series = [m for m in time_series if m.get("confidence_source") != "heuristic_fallback"]
        if not time_series or len(time_series) < 2:
            return {
                "insufficient_data": True,
                "velocity": None,
                "time_span_years": None
            }

        def parse_date(m):
            return datetime.date.fromisoformat(self._get_date(m))

        sorted_ts = sorted(time_series, key=parse_date)
        prev = sorted_ts[-2]
        curr = sorted_ts[-1]

        if prev.get("measurement_type") != curr.get("measurement_type"):
            return {
                "insufficient_data": True,
                "velocity": None,
                "time_span_years": None,
                "reason": "Mismatch in measurement types between compared visits."
            }

        if any(m.get("alignment_status") == "failed" for m in [prev, curr]):
            return {
                "insufficient_data": True,
                "velocity": None,
                "time_span_years": None,
                "alignment_status": "failed",
                "reason": "Alignment failed."
            }

        date_prev = parse_date(prev)
        date_curr = parse_date(curr)
        days = (date_curr - date_prev).days

        if days <= 0:
            return {
                "insufficient_data": True,
                "velocity": 0.0,
                "time_span_years": 0.0,
                "message": "Zero or negative time interval between measurements"
            }

        time_span_years = days / 365.25
        val_prev = self._get_val(prev)
        val_curr = self._get_val(curr)
        velocity = (val_curr - val_prev) / time_span_years

        return {
            "insufficient_data": False,
            "velocity": round(velocity, 4),
            "time_span_years": round(time_span_years, 3),
            "val_prev": val_prev,
            "val_curr": val_curr,
            "date_prev": self._get_date(prev),
            "date_curr": self._get_date(curr)
        }

    def compute_absolute_and_relative_change(self, time_series: list) -> dict:
        """
        Compute absolute percentage-point/mm change and relative percentage change.
        """
        time_series = [m for m in time_series if m.get("confidence_source") != "heuristic_fallback"]
        if not time_series or len(time_series) < 2:
            return {
                "insufficient_data": True,
                "absolute_change": None,
                "relative_change_pct": None
            }

        def parse_date(m):
            return datetime.date.fromisoformat(self._get_date(m))

        sorted_ts = sorted(time_series, key=parse_date)
        prev = sorted_ts[0]
        curr = sorted_ts[-1]

        if prev.get("measurement_type") != curr.get("measurement_type"):
            return {
                "insufficient_data": True,
                "absolute_change": None,
                "relative_change_pct": None,
                "reason": "Mismatch in measurement types between compared visits."
            }

        if any(m.get("alignment_status") == "failed" for m in [prev, curr]):
            return {
                "insufficient_data": True,
                "absolute_change": None,
                "relative_change_pct": None,
                "alignment_status": "failed",
                "reason": "Alignment failed."
            }

        val_prev = self._get_val(prev)
        val_curr = self._get_val(curr)

        absolute_change = val_curr - val_prev

        if val_prev == 0:
            relative_change_pct = 0.0
        else:
            relative_change_pct = (absolute_change / val_prev) * 100.0

        return {
            "insufficient_data": False,
            "absolute_change": round(absolute_change, 4),
            "relative_change_pct": round(relative_change_pct, 2),
            "val_prev": val_prev,
            "val_curr": val_curr
        }

    def fit_multi_interval_trend(self, time_series: list, acceleration_threshold_multiplier: float = 1.5) -> dict:
        """
        Fit linear trend across all points (3+ required).
        Detect accelerated episodes (interval slope > multiplier * baseline average slope).
        """
        time_series = [m for m in time_series if m.get("confidence_source") != "heuristic_fallback"]
        if not time_series or len(time_series) < 3:
            return {
                "status": "insufficient_data",
                "message": "Fewer than 3 timepoints available for trend fitting",
                "linear_slope": None,
                "linear_intercept": None,
                "is_accelerating": False,
                "accelerated_episodes": []
            }

        # Check measurement type homogeneity
        m_types = {m.get("measurement_type") for m in time_series}
        if len(m_types) > 1:
            return {
                "status": "insufficient_data",
                "message": "Mismatch in measurement types across time series",
                "linear_slope": None,
                "linear_intercept": None,
                "is_accelerating": False,
                "accelerated_episodes": []
            }

        # Check alignment confidence gate
        if any(m.get("alignment_status") == "failed" for m in time_series):
            return {
                "status": "insufficient_data",
                "message": "Alignment failed.",
                "linear_slope": None,
                "linear_intercept": None,
                "is_accelerating": False,
                "accelerated_episodes": [],
                "alignment_status": "failed"
            }

        import numpy as np

        def parse_date(m):
            return datetime.date.fromisoformat(self._get_date(m))

        sorted_ts = sorted(time_series, key=parse_date)
        start_date = parse_date(sorted_ts[0])

        x = []
        y = []
        for m in sorted_ts:
            dt = parse_date(m)
            years = (dt - start_date).days / 365.25
            x.append(years)
            y.append(self._get_val(m))

        x = np.array(x)
        y = np.array(y)

        # Fit overall linear regression
        slope, intercept = np.polyfit(x, y, 1)

        is_accelerating = False
        accelerated_episodes = []
        baseline_slope = max(0.01, slope)

        for i in range(len(x) - 1):
            dx = x[i+1] - x[i]
            if dx <= 0:
                continue
            segment_slope = (y[i+1] - y[i]) / dx

            if segment_slope > (acceleration_threshold_multiplier * baseline_slope):
                is_accelerating = True
                accelerated_episodes.append({
                    "interval_start_date": self._get_date(sorted_ts[i]),
                    "interval_end_date": self._get_date(sorted_ts[i+1]),
                    "segment_slope": round(segment_slope, 4),
                    "baseline_slope": round(slope, 4),
                    "ratio": round(segment_slope / baseline_slope, 2)
                })

        trend_classification = "stable"
        if slope > 0.25:
            trend_classification = "slow progression"
        if is_accelerating:
            trend_classification = "accelerating"
        if slope < -0.1:
            trend_classification = "improving"

        return {
            "status": "success",
            "linear_slope": round(float(slope), 4),
            "linear_intercept": round(float(intercept), 4),
            "trend_classification": trend_classification,
            "is_accelerating": is_accelerating,
            "accelerated_episodes": accelerated_episodes,
            "x_years": x.tolist(),
            "y_values": y.tolist()
        }

    def compute_statistical_confidence(self, time_series: list) -> dict:
        """
        Computes structured confidence metrics propagating landmark and alignment scores.
        """
        time_series = [m for m in time_series if m.get("confidence_source") != "heuristic_fallback"]
        if not time_series or len(time_series) < 2:
            return {
                "qualitative_confidence": "insufficient_data",
                "uncertainty_range": None,
                "data_quality_flags": ["insufficient_points"]
            }

        low_conf_threshold = 0.7
        data_quality_flags = []

        landmark_confs = [m.get("landmark_confidence", 1.0) for m in time_series]
        alignment_confs = [m.get("alignment_confidence", 1.0) for m in time_series]

        min_landmark_conf = min(landmark_confs)
        min_alignment_conf = min(alignment_confs)

        if min_landmark_conf < low_conf_threshold:
            data_quality_flags.append("low_landmark_confidence")
        if min_alignment_conf < low_conf_threshold:
            data_quality_flags.append("low_alignment_confidence")

        def parse_date(m):
            return datetime.date.fromisoformat(self._get_date(m))
        sorted_ts = sorted(time_series, key=parse_date)
        time_span = (parse_date(sorted_ts[-1]) - parse_date(sorted_ts[0])).days / 365.25
        if time_span < 1.0:
            data_quality_flags.append("short_duration_under_1yr")

        if len(data_quality_flags) == 0:
            qualitative_confidence = "high"
        elif len(data_quality_flags) == 1:
            qualitative_confidence = "moderate"
        else:
            qualitative_confidence = "low"

        return {
            "qualitative_confidence": qualitative_confidence,
            "data_quality_flags": data_quality_flags,
            "min_landmark_confidence": round(min_landmark_conf, 2),
            "min_alignment_confidence": round(min_alignment_conf, 2)
        }

    def compute_talpa_profile(self, time_series: list, acceleration_threshold_multiplier: float = 1.5) -> dict:
        """
        Unified TALPA computation method producing a structured, confidence-annotated result.
        """
        time_series = [m for m in time_series if m.get("confidence_source") != "heuristic_fallback"]
        if not time_series or len(time_series) < 2:
            return {
                "status": "insufficient_data",
                "velocity": None,
                "absolute_change": None,
                "relative_change_pct": None,
                "trend": {
                    "trend_classification": "insufficient_data",
                    "is_accelerating": False
                },
                "confidence": {
                    "qualitative_confidence": "insufficient_data",
                    "data_quality_flags": ["insufficient_points"]
                },
                "based_on_n_points": len(time_series) if time_series else 0
            }

        # Check measurement type homogeneity
        m_types = {m.get("measurement_type") for m in time_series}
        if len(m_types) > 1:
            return {
                "status": "insufficient_data",
                "velocity": None,
                "absolute_change": None,
                "relative_change_pct": None,
                "trend": {
                    "trend_classification": "insufficient_data",
                    "is_accelerating": False
                },
                "confidence": {
                    "qualitative_confidence": "insufficient_data",
                    "data_quality_flags": ["measurement_type_mismatch"]
                },
                "based_on_n_points": len(time_series)
            }

        # Check alignment confidence gate
        if any(m.get("alignment_status") == "failed" for m in time_series):
            return {
                "status": "insufficient_data",
                "velocity": None,
                "absolute_change": None,
                "relative_change_pct": None,
                "trend": {
                    "trend_classification": "insufficient_data",
                    "is_accelerating": False
                },
                "confidence": {
                    "qualitative_confidence": "insufficient_data",
                    "data_quality_flags": ["alignment_failed"]
                },
                "based_on_n_points": len(time_series)
            }

        vel_info = self.compute_progression_velocity(time_series)
        if vel_info.get("insufficient_data"):
            reason = vel_info.get("reason", "insufficient_points")
            flag = "alignment_failed" if "alignment" in reason.lower() else ("measurement_type_mismatch" if "measurement" in reason.lower() else "insufficient_points")
            return {
                "status": "insufficient_data",
                "velocity": None,
                "absolute_change": None,
                "relative_change_pct": None,
                "trend": {
                    "trend_classification": "insufficient_data",
                    "is_accelerating": False
                },
                "confidence": {
                    "qualitative_confidence": "insufficient_data",
                    "data_quality_flags": [flag]
                },
                "based_on_n_points": len(time_series)
            }

        change_info = self.compute_absolute_and_relative_change(time_series)
        trend_info = self.fit_multi_interval_trend(time_series, acceleration_threshold_multiplier)
        conf_info = self.compute_statistical_confidence(time_series)

        if trend_info["status"] == "success":
            trend_classification = trend_info["trend_classification"]
        else:
            v = vel_info["velocity"]
            if v < 0.1:
                trend_classification = "stable"
            elif v < 0.5:
                trend_classification = "slow progression"
            else:
                trend_classification = "rapid progression"

            if v < -0.1:
                trend_classification = "improving"

        return {
            "status": "success",
            "velocity": vel_info["velocity"],
            "absolute_change": change_info["absolute_change"],
            "relative_change_pct": change_info["relative_change_pct"],
            "trend": {
                "trend_classification": trend_classification,
                "is_accelerating": trend_info.get("is_accelerating", False),
                "linear_slope": trend_info.get("linear_slope"),
                "accelerated_episodes": trend_info.get("accelerated_episodes", [])
            },
            "confidence": conf_info,
            "based_on_n_points": len(time_series)
        }
