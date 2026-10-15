"""Security event taxonomy and detection rules.

The taxonomy test is the important one: it reads every event name the application
actually records and fails if any of them is unclassified, so a new event has to be
categorised when it is added rather than silently joining a pile of loose strings.
"""
import datetime as dt
import re
from pathlib import Path

import pytest

from app.security import events
from tests.conftest import UA, login

BACKEND = Path(__file__).resolve().parent.parent


def entry(action, actor="D-1", minutes_ago=0, outcome="success"):
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=minutes_ago)
    return {"action": action, "actor": actor, "outcome": outcome, "timestamp": when.isoformat()}


# ---------------------------------------------------------------- taxonomy ---
def recorded_action_names() -> set[str]:
    """Every literal event name passed to audit().record() in the application."""
    names = set()
    for path in (BACKEND / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        names.update(re.findall(r'record\(\s*"([A-Z][A-Z_0-9]*)"', text))
        # DOTALL, because a _deny() message can wrap across lines before the event name;
        # without it the guard silently misses those events.
        names.update(re.findall(r'_deny\(\s*\d+\s*,.*?,\s*"([A-Z][A-Z_0-9]*)"', text, re.S))
    return names


def test_every_recorded_event_is_classified():
    """An unclassified event is one nothing can alert on."""
    unknown = sorted(a for a in recorded_action_names()
                     if events.classify(a) == events.UNCLASSIFIED)
    assert not unknown, f"add these to TAXONOMY in app/security/events.py: {unknown}"


def test_taxonomy_has_no_entries_for_events_that_no_longer_exist():
    """Keeps the taxonomy honest as events are renamed or removed."""
    recorded = recorded_action_names()
    # Names raised by the Zero Trust guard and the test harness are recorded dynamically.
    dynamic = {"AUTH_MISSING", "AUTH_INVALID_TOKEN", "AUTH_SESSION_REJECTED", "AUTH_SESSION_IDLE",
               "AUTH_DEVICE_MISMATCH", "AUTH_ACCOUNT_BLOCKED", "PERMISSION_DENIED",
               "POLICY_UNCLASSIFIED_ROUTE", "LOGIN_FAILED", "PREDICTION"}
    stale = sorted(set(events.TAXONOMY) - recorded - dynamic)
    assert not stale, f"TAXONOMY lists events nothing records: {stale}"


def test_unknown_action_is_surfaced_not_dropped():
    assert events.classify("SOMETHING_BRAND_NEW") == events.UNCLASSIFIED


def test_prefixed_event_families_are_classified():
    assert events.classify("REVIEW_APPROVE")[0] == events.DATA
    assert events.classify("REVIEW_REJECT")[0] == events.DATA


# ------------------------------------------------------------------- rules ---
def test_repeated_login_failures_raise_one_alert():
    entries = [entry("LOGIN_FAILED", minutes_ago=i) for i in range(5)]
    alerts = {a.rule: a for a in events.detect(entries)}
    assert "repeated_login_failures" in alerts
    assert alerts["repeated_login_failures"].count == 5


def test_below_threshold_does_not_alert():
    assert not [a for a in events.detect([entry("LOGIN_FAILED") for _ in range(4)])
                if a.rule == "repeated_login_failures"]


def test_events_outside_the_window_do_not_count():
    old = [entry("LOGIN_FAILED", minutes_ago=60) for _ in range(10)]
    assert not [a for a in events.detect(old) if a.rule == "repeated_login_failures"]


def test_failures_are_counted_per_actor_not_in_total():
    """Four failures each from three accounts is not one account under attack."""
    entries = [entry("LOGIN_FAILED", actor=f"D-{i}") for i in range(3) for _ in range(4)]
    assert not [a for a in events.detect(entries) if a.rule == "repeated_login_failures"]


def test_authorization_probing_is_detected(client):
    """The S1 finding: refusals were audited but nothing added them up.

    The action names come from the rule itself rather than being retyped here, so the
    test follows the rule if its triggering events ever change, instead of silently
    testing an event the rule no longer watches.
    """
    rule = next(r for r in events.RULES if r.name == "authorization_probing")
    patient_denied, permission_denied = sorted(rule.actions)
    entries = [entry(patient_denied, minutes_ago=i % 4) for i in range(6)]
    entries += [entry(permission_denied, minutes_ago=i % 4) for i in range(5)]
    alerts = {a.rule: a for a in events.detect(entries)}
    assert "authorization_probing" in alerts
    assert alerts["authorization_probing"].count == 11
    assert alerts["authorization_probing"].actions == sorted(rule.actions)


def test_mass_patient_access_is_detected():
    entries = [entry("PATIENT_VIEWED", minutes_ago=i % 9) for i in range(30)]
    assert "mass_patient_access" in {a.rule for a in events.detect(entries)}


@pytest.mark.parametrize("action,rule", [
    ("MODEL_LOAD_REFUSED", "model_load_refused"),
    ("STORAGE_INTEGRITY_FAILURE", "stored_data_integrity_failure"),
    ("REFRESH_TOKEN_REUSE", "refresh_token_reuse"),
    ("HONEYPOT_TRIGGERED", "decoy_record_accessed"),
])
def test_single_occurrence_rules_alert_immediately(action, rule):
    """These never happen in normal operation, so one is already too many."""
    alerts = {a.rule: a for a in events.detect([entry(action)])}
    assert rule in alerts
    assert alerts[rule].severity == events.CRITICAL


def test_alerts_are_ordered_by_severity():
    entries = [entry("LOGIN_FAILED", minutes_ago=i) for i in range(5)] + [entry("HONEYPOT_TRIGGERED")]
    severities = [a.severity for a in events.detect(entries)]
    assert severities[0] == events.CRITICAL


def test_malformed_timestamps_do_not_crash_detection():
    entries = [{"action": "LOGIN_FAILED", "actor": "D-1", "timestamp": "not-a-date"},
               {"action": "LOGIN_FAILED", "actor": "D-1"}]
    assert events.detect(entries) == []


def test_summary_counts_by_category_and_severity():
    summary = events.summarise([entry("LOGIN_SUCCESS"), entry("LOGIN_FAILED"), entry("PATIENT_VIEWED")])
    assert summary["events"] == 3
    assert summary["by_category"][events.AUTH] == 2
    assert summary["by_category"][events.DATA] == 1
    assert summary["unclassified_actions"] == []


# -------------------------------------------------------------- endpoint ---
def test_events_endpoint_requires_the_security_permission(client):
    for role in ("dentist", "technician"):
        assert client.get("/api/security/events", headers=login(client, role)).status_code == 403
    for role in ("admin", "auditor"):
        assert client.get("/api/security/events", headers=login(client, role)).status_code == 200


def test_events_endpoint_is_unreachable_without_authentication(client):
    assert client.get("/api/security/events", headers=UA).status_code == 401


def test_events_endpoint_reports_detections_from_the_real_audit_log(client):
    """Drive real refusals through the API, then confirm they are detected."""
    dentist = login(client, "dentist")
    for _ in range(11):
        client.get("/api/admin/users", headers=dentist)  # PERMISSION_DENIED each time

    body = client.get("/api/security/events", headers=login(client, "auditor")).get_json()["data"]
    probing = [a for a in body["alerts"] if a["rule"] == "authorization_probing"]
    assert probing, f"no probing alert; rules fired: {[a['rule'] for a in body['alerts']]}"
    assert probing[0]["count"] >= 10
    assert body["summary"]["by_category"], "the summary classified nothing"
    # Completeness of the taxonomy is asserted statically by
    # test_every_recorded_event_is_classified, against the source. It is not asserted
    # here: this reads the shared audit log, into which sibling test modules write
    # synthetic events of their own, and those are not application events.


def test_events_endpoint_exposes_no_patient_data(client):
    """An auditor may read security state but never patient information."""
    dentist = login(client, "dentist")
    created = client.post("/api/patients", headers=dentist,
                          json={"name": "Eventful Patient", "age": 33, "contact": "5559999"})
    assert created.status_code == 201
    client.get(f"/api/patients/{created.get_json()['data']['patient_id']}", headers=dentist)

    raw = client.get("/api/security/events", headers=login(client, "auditor")).get_data(as_text=True)
    assert "Eventful Patient" not in raw
    assert "5559999" not in raw
