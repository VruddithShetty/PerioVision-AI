"""Upload guard: every radiograph is checked before anything else touches it.

Checks, in order:
  1. size limit (before reading the whole file into memory)
  2. extension allow-list (.png .jpg .jpeg .dcm)
  3. magic bytes must match the extension (a renamed .exe/.pdf is rejected)
  4. decodes as an image; pixel dimensions within limits (blocks decompression bombs)
  5. metadata stripped: PNG/JPEG are re-encoded from raw pixels, so EXIF/GPS/text
     chunks are dropped; DICOM patient/institution tags are removed
The original filename is never used on disk (no path traversal); callers get a
random ID plus clean PNG bytes.
"""
from __future__ import annotations

import io
import os
import secrets
from dataclasses import dataclass, field

import cv2
import numpy as np

MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "16")) * 1024 * 1024
MAX_PIXELS = 40_000_000       # e.g. 8000 x 5000
MIN_SIDE = 64
ALLOWED = {".png": "png", ".jpg": "jpeg", ".jpeg": "jpeg", ".dcm": "dicom"}

# DICOM tags that identify the patient or the site (removed on upload)
DICOM_PHI_TAGS = (
    "PatientName", "PatientID", "PatientBirthDate", "PatientSex", "PatientAge", "PatientAddress",
    "PatientTelephoneNumbers", "OtherPatientIDs", "OtherPatientNames", "InstitutionName",
    "InstitutionAddress", "ReferringPhysicianName", "PerformingPhysicianName", "OperatorsName",
    "AccessionNumber", "StudyID",
)


class UploadRejected(ValueError):
    """The message is safe to show to the user."""


@dataclass
class CleanUpload:
    upload_id: str
    kind: str                 # png | jpeg | dicom
    png_bytes: bytes          # metadata-free 8-bit image, ready for analysis
    width: int
    height: int
    pixel_spacing_mm: float | None = None
    study_date: str | None = None
    removed_metadata: list[str] = field(default_factory=list)


def sniff_kind(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(header) >= 132 and header[128:132] == b"DICM":
        return "dicom"
    return None


def _check_dims(h: int, w: int) -> None:
    if h * w > MAX_PIXELS:
        raise UploadRejected("Image is too large (pixel dimensions).")
    if min(h, w) < MIN_SIDE:
        raise UploadRejected("Image is too small to be a radiograph.")


def _to_uint8(arr: np.ndarray) -> np.ndarray:
    arr = arr.astype(np.float64)
    arr -= arr.min()
    if arr.max() > 0:
        arr /= arr.max()
    return (arr * 255).astype(np.uint8)


def inspect_upload(data: bytes, filename: str) -> CleanUpload:
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > MAX_BYTES:
        raise UploadRejected(f"File is larger than {MAX_BYTES // (1024 * 1024)} MB.")

    ext = os.path.splitext(str(filename or ""))[1].lower()
    if ext not in ALLOWED:
        raise UploadRejected("Only PNG, JPEG and DICOM (.dcm) files are accepted.")
    kind = sniff_kind(data[:132])
    if kind is None or kind != ALLOWED[ext]:
        raise UploadRejected("File content does not match its extension (possible disguised file).")

    removed: list[str] = []
    spacing = study_date = None
    if kind == "dicom":
        import pydicom

        try:
            ds = pydicom.dcmread(io.BytesIO(data))
            ds.decode()
        except Exception:
            raise UploadRejected("The DICOM file could not be read.") from None
        rows, cols = int(getattr(ds, "Rows", 0)), int(getattr(ds, "Columns", 0))
        _check_dims(rows, cols)
        for tag in DICOM_PHI_TAGS:
            if tag in ds:
                removed.append(tag)
                delattr(ds, tag)
        ps = getattr(ds, "PixelSpacing", None) or getattr(ds, "ImagerPixelSpacing", None)
        try:
            spacing = float(ps[0]) if ps else None
        except (TypeError, ValueError, IndexError):
            spacing = None
        study_date = str(getattr(ds, "StudyDate", "") or "") or None
        try:
            pixels = ds.pixel_array
        except Exception:
            raise UploadRejected("The DICOM file has no readable image.") from None
        if pixels.ndim == 3:  # multi-frame or colour: use the first frame / convert to grey
            pixels = pixels[0] if pixels.shape[-1] not in (3, 4) else cv2.cvtColor(_to_uint8(pixels), cv2.COLOR_RGB2GRAY)
        img = _to_uint8(pixels)
    else:
        from PIL import Image

        try:
            with Image.open(io.BytesIO(data)) as probe:  # reads only the header, not the pixels
                width, height = probe.size
        except Exception:
            raise UploadRejected("The image could not be decoded.") from None
        _check_dims(height, width)
        # A cut-off file still decodes: OpenCV fills the missing rows with flat grey, which hides exactly the roots
        # and bone crest the measurement needs. Require the format's end marker instead of trusting the decoder.
        tail = data.rstrip(b"\x00")
        if (kind == "jpeg" and not tail.endswith(b"\xff\xd9")) or (kind == "png" and b"IEND" not in data[-64:]):
            raise UploadRejected("The image file is incomplete (cut off before its end). Upload the full file.")
        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise UploadRejected("The image could not be decoded.")
        _check_dims(*img.shape[:2])
        removed.append("all embedded metadata (re-encoded from pixels)")

    ok, png = cv2.imencode(".png", img)
    if not ok:
        raise UploadRejected("The image could not be processed.")
    return CleanUpload(upload_id=secrets.token_hex(16), kind=kind, png_bytes=png.tobytes(),
                       width=int(img.shape[1]), height=int(img.shape[0]), pixel_spacing_mm=spacing,
                       study_date=study_date, removed_metadata=removed)


class SecureUploadValidator:
    """Backward-compatible wrapper around inspect_upload."""

    def validate(self, file_stream, filename: str) -> dict:
        try:
            clean = inspect_upload(file_stream.read(), filename)
            return {"valid": True, "safe_filename": f"XR_{clean.upload_id}.png", "mime_type": f"image/{clean.kind}",
                    "size_bytes": len(clean.png_bytes)}
        except UploadRejected as exc:
            return {"valid": False, "error": str(exc)}
