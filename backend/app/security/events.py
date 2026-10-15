"""Security event taxonomy and detection over the audit log.

The audit log already records who did what, when, to which resource and with what
result. What it could not do was answer "is something wrong right now?": a single
refused request is routine, while thirty in a minute from one account is someone
working through patient identifiers.

Two pieces, both deliberately small:

  TAXONOMY   every event name the application records, mapped to a category and a
             severity. Nothing is recorded uncategorised: a test asserts that every
             action name in the codebase appears here, so a new event has to be
             classified when it is added rather than quietly joining a pile of
             unlabelled strings.

  RULES      windowed thresholds over those events. A rule counts matching entries
             inside a time window, grouped by actor, and raises an alert when the
             count reaches its threshold.

This reads the existing audit log rather than introducing a second store, which
means detection inherits the log's tamper-evidence: an attacker who wants to hide
a burst of failures has to defeat the hash chain to do it. There is no daemon and
no new persistence - alerts are computed on demand from entries already written.
It is intentionally not a SIEM; it is a clean set of signals a SIEM could consume.

Alerts carry actor IDs, counts and event names. They never carry PHI, because the
events themselves do not: patient resources are recorded as pseudonyms.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

# ----------------------------------------------------------------- taxonomy ---
AUTH = "AUTH"                      # proving who you are
AUTHZ = "AUTHZ"                    # deciding what you may do
SESSION = "SESSION"                # session and token lifecycle
DATA = "DATA"                      # patient and clinical records
MODEL = "MODEL"                    # model loading and integrity
UPLOAD = "UPLOAD"                  # inbound files
CRYPTO = "CRYPTO"                  # stored-data integrity
AUDIT = "AUDIT"                    # the trail itself
ADMIN = "ADMIN"                    # account and system administration
INFRASTRUCTURE = "INFRASTRUCTURE"  # process lifecycle
DECEPTION = "DECEPTION"            # decoy records

INFO, NOTICE, WARNING, CRITICAL = "info", "notice", "warning", "critical"

# action -> (category, severity). Severity is the weight of a *single* occurrence;
# a rule can still raise a high-severity alert from repeated low-severity events.
TAXONOMY: dict[str, tuple[str, str]] = {
    # --- authentication ---
    "LOGIN_SUCCESS":             (AUTH, INFO),
    "LOGIN_FAILED":              (AUTH, NOTICE),
    "LOGIN_LOCKED":              (AUTH, WARNING),
    "LOGOUT":                    (AUTH, INFO),
    "MFA_ENABLED":               (AUTH, INFO),
    "MFA_DISABLED":              (AUTH, WARNING),
    "MFA_ENROLMENT_STARTED":     (AUTH, INFO),
    "MFA_FAILED":                (AUTH, NOTICE),
    "AUTH_MISSING":              (AUTH, INFO),
    "AUTH_INVALID_TOKEN":        (AUTH, NOTICE),
    "AUTH_ACCOUNT_BLOCKED":      (AUTH, WARNING),
    "AUTH_MFA_ENROLMENT_REQUIRED": (AUTH, NOTICE),
    # --- sessions ---
    "AUTH_SESSION_REJECTED":     (SESSION, NOTICE),
    "AUTH_SESSION_IDLE":         (SESSION, INFO),
    "AUTH_DEVICE_MISMATCH":      (SESSION, WARNING),
    "REFRESH_TOKEN_REUSE":       (SESSION, CRITICAL),
    # --- authorization ---
    "PERMISSION_DENIED":         (AUTHZ, NOTICE),
    "PATIENT_ACCESS_DENIED":     (AUTHZ, WARNING),
    "POLICY_UNCLASSIFIED_ROUTE": (AUTHZ, WARNING),
    # --- patient and clinical data ---
    "PATIENT_CREATED":           (DATA, INFO),
    "PATIENT_VIEWED":            (DATA, INFO),
    "PATIENT_UPDATED":           (DATA, INFO),
    "PATIENT_LIST":              (DATA, INFO),
    "CARE_TEAM_ADDED":           (DATA, NOTICE),
    "CARE_PLAN_VIEWED":          (DATA, INFO),
    "PERIO_CHART_VIEWED":        (DATA, INFO),
    "PERIO_CHART_SAVED":         (DATA, INFO),
    "PROGRESSION_VIEWED":        (DATA, INFO),
    "RECALL_BOARD_VIEWED":       (DATA, INFO),
    "ANALYSIS_VIEWED":           (DATA, INFO),
    "GRADCAM_TOOTH_VIEWED":      (DATA, INFO),
    "ANALYSIS_FAILED":           (DATA, NOTICE),
    "ANALYSIS_REJECTED_QUALITY": (DATA, INFO),
    "PREDICTION":                (DATA, INFO),
    "REPORT_GENERATED":          (DATA, INFO),
    "REPORT_DOWNLOADED":         (DATA, INFO),
    "REPORT_VERIFIED":           (DATA, INFO),
    # --- uploads ---
    "UPLOAD_ACCEPTED":           (UPLOAD, INFO),
    "UPLOAD_BLOCKED":            (UPLOAD, NOTICE),
    # --- models ---
    "MODEL_LOADED":              (MODEL, INFO),
    "MODEL_LOAD_REFUSED":        (MODEL, CRITICAL),
    # The model passed both gates and still returned something other than its recorded
    # output, so the bytes are right and the behaviour is not. Critical for the same
    # reason a refusal is: nothing downstream should be trusted until it is explained.
    "MODEL_SELF_CHECK_FAILED":   (MODEL, CRITICAL),
    # Production refusing to analyse rather than falling back to the demo heuristic.
    # Not an attack by itself, but a run of these means no verified model is loading.
    "ANALYSIS_REFUSED_NO_MODEL": (MODEL, WARNING),
    # --- stored data integrity ---
    "STORAGE_INTEGRITY_FAILURE": (CRYPTO, CRITICAL),
    # --- the audit trail ---
    "AUDIT_CHAIN_VERIFIED":      (AUDIT, INFO),
    "RETENTION_PURGE":           (DATA, NOTICE),
    # --- administration ---
    "USER_CREATED":              (ADMIN, NOTICE),
    "USER_UPDATED":              (ADMIN, NOTICE),
    "USER_LOCKED":               (ADMIN, WARNING),
    "SECURITY_LAB_RUN":          (ADMIN, INFO),
    # --- infrastructure ---
    "SYSTEM_START":              (INFRASTRUCTURE, INFO),
    # --- deception ---
    "HONEYPOT_TRIGGERED":        (DECEPTION, CRITICAL),
}

# Families whose names carry a variable suffix (REVIEW_APPROVE, REVIEW_REJECT, ...).
PREFIX_TAXONOMY: tuple[tuple[str, tuple[str, str]], ...] = (
    ("REVIEW_", (DATA, INFO)),
    ("LAB_EVENT_", (ADMIN, INFO)),
)

UNCLASSIFIED = ("UNCLASSIFIED", NOTICE)


def classify(action: str) -> tuple[str, str]:
    """Category and severity for an action. Unknown actions are surfaced, not dropped."""
    if action in TAXONOMY:
        return TAXONOMY[action]
    for prefix, value in PREFIX_TAXONOMY:
        if action.startswith(prefix):
            return value
    return UNCLASSIFIED


# ------------------------------------------------------------------- rules ---
@dataclass(frozen=True)
class Rule:
    name: str
    description: str
    actions: frozenset[str]
    threshold: int
    window: dt.timedelta
    severity: str
    group_by: str = "actor"
    # Only count entries whose outcome is one of these; None counts every outcome.
    outcomes: frozenset[str] | None = None


MINUTES = dt.timedelta(minutes=1)

RULES: tuple[Rule, ...] = (
    Rule("repeated_login_failures",
         "Several failed logins for one account in a short window (credential guessing).",
         frozenset({"LOGIN_FAILED"}), 5, 10 * MINUTES, WARNING),

    Rule("repeated_mfa_failures",
         "Repeated TOTP failures: the password may already be known.",
         frozenset({"MFA_FAILED"}), 5, 10 * MINUTES, WARNING),

    Rule("authorization_probing",
         "An account repeatedly asking for things it may not have. One refusal is a "
         "mistake; many in a few minutes is someone mapping what they can reach.",
         frozenset({"PERMISSION_DENIED", "PATIENT_ACCESS_DENIED"}), 10, 5 * MINUTES, WARNING),

    Rule("mass_patient_access",
         "One account opening an unusual number of patient records (bulk exfiltration).",
         frozenset({"PATIENT_VIEWED"}), 30, 10 * MINUTES, WARNING),

    Rule("repeated_upload_rejections",
         "Many rejected uploads from one account: someone probing the upload guard.",
         frozenset({"UPLOAD_BLOCKED"}), 5, 10 * MINUTES, WARNING),

    Rule("burst_of_administrative_changes",
         "An unusual number of account changes in one window.",
         frozenset({"USER_CREATED", "USER_UPDATED", "USER_LOCKED"}), 5, 10 * MINUTES, NOTICE),

    Rule("session_device_mismatches",
         "Tokens presented from a device the session was not bound to.",
         frozenset({"AUTH_DEVICE_MISMATCH"}), 3, 10 * MINUTES, WARNING),

    # Single-occurrence rules: these should never happen in normal operation.
    Rule("model_load_refused",
         "A model failed integrity or approval and was refused.",
         frozenset({"MODEL_LOAD_REFUSED"}), 1, 24 * 60 * MINUTES, CRITICAL),

    Rule("model_self_check_failed",
         "A loaded model returned something other than its recorded output. Kept apart "
         "from model_load_refused: that one never got past the gate, this one did.",
         frozenset({"MODEL_SELF_CHECK_FAILED"}), 1, 24 * 60 * MINUTES, CRITICAL),

    Rule("stored_data_integrity_failure",
         "Stored ciphertext failed its authentication tag: tampering or corruption.",
         frozenset({"STORAGE_INTEGRITY_FAILURE"}), 1, 24 * 60 * MINUTES, CRITICAL),

    Rule("refresh_token_reuse",
         "A refresh token was presented twice, which means one copy was stolen.",
         frozenset({"REFRESH_TOKEN_REUSE"}), 1, 24 * 60 * MINUTES, CRITICAL),

    Rule("decoy_record_accessed",
         "A decoy patient was opened. Real workflows never reach these records.",
         frozenset({"HONEYPOT_TRIGGERED"}), 1, 24 * 60 * MINUTES, CRITICAL),

    Rule("unclassified_route_reached",
         "A route without an access decision was requested; it failed closed.",
         frozenset({"POLICY_UNCLASSIFIED_ROUTE"}), 1, 60 * MINUTES, WARNING),
)


@dataclass
class Alert:
    rule: str
    description: str
    severity: str
    actor: str
    count: int
    window_minutes: int
    first_seen: str | None = None
    last_seen: str | None = None
    actions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _parse(ts: str | None) -> dt.datetime | None:
    if not ts:
        return None
    try:
        parsed = dt.datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def detect(entries: list[dict], now: dt.datetime | None = None) -> list[Alert]:
    """Run every rule over audit entries. Newest-first or oldest-first both work."""
    now = now or dt.datetime.now(dt.timezone.utc)
    alerts: list[Alert] = []

    for rule in RULES:
        buckets: dict[str, list[dict]] = {}
        cutoff = now - rule.window
        for entry in entries:
            if entry.get("action") not in rule.actions:
                continue
            if rule.outcomes and entry.get("outcome") not in rule.outcomes:
                continue
            when = _parse(entry.get("timestamp"))
            if when is None or when < cutoff:
                continue
            buckets.setdefault(str(entry.get(rule.group_by) or "unknown"), []).append(entry)

        for actor, matched in buckets.items():
            if len(matched) < rule.threshold:
                continue
            stamps = sorted(e["timestamp"] for e in matched if e.get("timestamp"))
            alerts.append(Alert(
                rule=rule.name, description=rule.description, severity=rule.severity,
                actor=actor, count=len(matched),
                window_minutes=int(rule.window.total_seconds() // 60),
                first_seen=stamps[0] if stamps else None,
                last_seen=stamps[-1] if stamps else None,
                actions=sorted({e["action"] for e in matched}),
            ))

    order = {CRITICAL: 0, WARNING: 1, NOTICE: 2, INFO: 3}
    alerts.sort(key=lambda a: (order.get(a.severity, 9), -a.count))
    return alerts


def summarise(entries: list[dict]) -> dict:
    """Counts by category and severity, for the security dashboard."""
    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    unclassified: set[str] = set()
    for entry in entries:
        action = entry.get("action", "")
        category, severity = classify(action)
        by_category[category] = by_category.get(category, 0) + 1
        by_severity[severity] = by_severity.get(severity, 0) + 1
        if category == UNCLASSIFIED[0]:
            unclassified.add(action)
    return {"events": len(entries), "by_category": by_category, "by_severity": by_severity,
            "unclassified_actions": sorted(unclassified)}
