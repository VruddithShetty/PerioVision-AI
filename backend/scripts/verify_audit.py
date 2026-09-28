"""Verify the tamper-evident audit log and print the first tampered entry, if any.

Usage (from backend/):  python scripts/verify_audit.py
Exit code 0 = intact, 1 = tampering detected. In demo mode the log lives in memory,
so this is mainly useful with DB_MODE=production (or from the Security Lab page).
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))  # backend/

from app.security.audit_log import audit  # noqa: E402


def main() -> int:
    result = audit().verify_chain_integrity()
    print(json.dumps({k: v for k, v in result.items() if k != "anchors"}, indent=2, default=str))
    if result["chain_intact"]:
        print(f"\nAudit chain intact: {result['entries_verified']} entries and {result['anchors_checked']} anchors verified.")
        return 0
    print(f"\nTAMPERING DETECTED at entry {result['first_tampered_seq']}: {result['reason']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
