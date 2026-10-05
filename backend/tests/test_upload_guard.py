"""Upload guard: disguised files, wrong magic bytes, oversized images and metadata are handled."""
import io

import cv2
import numpy as np
import pytest
from PIL import Image

from app.security import upload_guard
from app.security.upload_guard import UploadRejected, inspect_upload
from tests.conftest import synthetic_radiograph


def test_valid_png_is_accepted_and_reencoded():
    clean = inspect_upload(synthetic_radiograph(), "scan.png")
    assert clean.kind == "png" and clean.width == 1400
    assert clean.png_bytes.startswith(b"\x89PNG")
    assert len(clean.upload_id) == 32


def test_exe_renamed_to_png_is_blocked():
    with pytest.raises(UploadRejected, match="does not match"):
        inspect_upload(b"MZ\x90\x00" + b"\x00" * 500, "xray.png")


def test_pdf_renamed_to_jpg_is_blocked():
    with pytest.raises(UploadRejected):
        inspect_upload(b"%PDF-1.7\n" + b"0" * 500, "xray.jpg")


def test_disallowed_extension_and_traversal_name():
    with pytest.raises(UploadRejected, match="Only PNG"):
        inspect_upload(synthetic_radiograph(), "../../etc/passwd")
    with pytest.raises(UploadRejected):
        inspect_upload(synthetic_radiograph(), "scan.svg")


def test_size_and_dimension_limits(monkeypatch):
    monkeypatch.setattr(upload_guard, "MAX_BYTES", 1000)
    with pytest.raises(UploadRejected, match="larger than"):
        inspect_upload(synthetic_radiograph(), "scan.png")
    monkeypatch.setattr(upload_guard, "MAX_BYTES", 50 * 1024 * 1024)
    monkeypatch.setattr(upload_guard, "MAX_PIXELS", 10_000)
    with pytest.raises(UploadRejected, match="too large"):
        inspect_upload(synthetic_radiograph(), "scan.png")


def test_tiny_image_is_rejected():
    ok, buf = cv2.imencode(".png", np.zeros((20, 20), np.uint8))
    with pytest.raises(UploadRejected, match="too small"):
        inspect_upload(buf.tobytes(), "tiny.png")


def test_exif_metadata_is_stripped():
    img = Image.fromarray(np.full((300, 600), 120, np.uint8)).convert("RGB")
    exif = Image.Exif()
    exif[0x010E] = "Patient: Jane Example, DOB 1980-01-01"   # ImageDescription
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif.tobytes())
    raw = buf.getvalue()
    assert b"Jane Example" in raw
    clean = inspect_upload(raw, "photo.jpg")
    assert b"Jane Example" not in clean.png_bytes
    assert Image.open(io.BytesIO(clean.png_bytes)).getexif().get(0x010E) is None


@pytest.mark.parametrize("ext,fraction", [(".jpg", 0.5), (".jpg", 0.8), (".jpg", 0.97), (".png", 0.8)])
def test_cut_off_image_is_rejected(ext, fraction):
    """A truncated file decodes with its missing rows as flat grey (hiding roots and crest); it must be refused."""
    img = (np.random.default_rng(0).random((600, 900)) * 255).astype(np.uint8)  # audit-ok: test image
    ok, buf = cv2.imencode(ext, img)
    data = buf.tobytes()
    inspect_upload(data, "film" + ext)                                       # the complete file is fine
    with pytest.raises(UploadRejected, match="incomplete|decoded"):
        inspect_upload(data[: int(len(data) * fraction)], "film" + ext)
