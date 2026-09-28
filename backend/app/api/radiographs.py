"""Radiograph upload: runs the upload guard and a quality preview, then stores the clean image encrypted."""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, g, request

from app.api._common import fail, ok
from app.extensions import limiter
from app.ml.preprocessing.quality_check import assess_quality
from app.models.connection import db
from app.security.audit_log import audit
from app.security.upload_guard import UploadRejected, inspect_upload
from app.security.zero_trust import secured
from app.services import storage_service

bp = Blueprint("radiographs", __name__)
UPLOAD_TTL = dt.timedelta(hours=2)


def uploads():
    return db["uploads"]


@bp.post("/api/radiographs")
@secured("radiograph:upload")
@limiter.limit("20 per minute")
def upload():
    file = request.files.get("image")
    if file is None:
        return fail(400, "Attach the radiograph as form field 'image'.")
    data = file.read()
    try:
        clean = inspect_upload(data, file.filename)
    except UploadRejected as exc:
        audit().record("UPLOAD_BLOCKED", outcome="denied", actor=g.user["id"], details={"reason": str(exc)})
        return fail(415, str(exc))

    import cv2
    import numpy as np

    gray = cv2.imdecode(np.frombuffer(clean.png_bytes, np.uint8), cv2.IMREAD_GRAYSCALE)
    quality = assess_quality(gray)
    blob_id = storage_service.put(clean.png_bytes, "upload")
    uploads().insert_one({
        "upload_id": clean.upload_id, "blob": blob_id, "owner": g.user["id"], "kind": clean.kind,
        "width": clean.width, "height": clean.height, "pixel_spacing_mm": clean.pixel_spacing_mm,
        "study_date": clean.study_date, "removed_metadata": clean.removed_metadata, "quality": quality,
        "expires": (dt.datetime.now(dt.timezone.utc) + UPLOAD_TTL).isoformat(), "used": False,
    })
    audit().record("UPLOAD_ACCEPTED", actor=g.user["id"],
                   details={"kind": clean.kind, "size": [clean.width, clean.height],
                            "metadata_removed": len(clean.removed_metadata)})
    return ok({"upload_id": clean.upload_id, "kind": clean.kind, "width": clean.width, "height": clean.height,
               "pixel_spacing_mm": clean.pixel_spacing_mm, "study_date": clean.study_date,
               "removed_metadata": clean.removed_metadata, "quality": quality}, 201)


def take_upload(upload_id: str, user_id: str) -> dict | None:
    """Claim an upload for analysis (owner only, once, before it expires)."""
    doc = uploads().find_one({"upload_id": str(upload_id), "owner": str(user_id), "used": False})
    if not doc or dt.datetime.fromisoformat(doc["expires"]) < dt.datetime.now(dt.timezone.utc):
        return None
    uploads().update_one({"upload_id": doc["upload_id"]}, {"$set": {"used": True}})
    doc["png_bytes"] = storage_service.get(doc["blob"], "upload")
    return doc
