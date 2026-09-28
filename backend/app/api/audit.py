"""Audit-log routes: browse entries, verify the hash chain and anchors, publish a Merkle root."""
from __future__ import annotations

from flask import Blueprint, g, request

from app.api._common import ok
from app.security.audit_log import audit
from app.security.zero_trust import secured

bp = Blueprint("audit", __name__)


@bp.get("/api/audit/logs")
@secured("audit:read")
def logs():
    limit = min(max(int(request.args.get("limit", 50) or 50), 1), 500)
    action = (request.args.get("action") or "").strip()[:64] or None
    actor = (request.args.get("actor") or "").strip()[:64] or None
    return ok(audit().recent(limit, action=action, actor=actor))


@bp.get("/api/audit/verify")
@secured("audit:verify")
def verify():
    result = audit().verify_chain_integrity()
    audit().record("AUDIT_CHAIN_VERIFIED", outcome="intact" if result["chain_intact"] else "tampered",
                   actor=g.user["id"], details={"first_tampered_seq": result["first_tampered_seq"]})
    return ok(result)


@bp.post("/api/audit/anchor")
@secured("audit:verify")
def anchor():
    return ok(audit().publish_root(actor=g.user["id"]), 201)
