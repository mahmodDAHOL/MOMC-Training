import io

import pytest
from PIL import Image

from momc_training.utils.uploads import UploadRejected, sanitise

MB = 1024 * 1024


def png(w=800, h=500):
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (28, 97, 93)).save(buf, "PNG")
    return buf.getvalue()


def test_image_is_reencoded_as_jpeg_and_capped():
    out, ext = sanitise(png(4000, 2500), "id_front", 10 * MB)
    assert ext == "jpg" and out[:3] == b"\xff\xd8\xff"
    assert max(Image.open(io.BytesIO(out)).size) == 2400


def test_exif_is_dropped():
    buf = io.BytesIO()
    img = Image.new("RGB", (800, 500))
    exif = img.getexif()
    exif[0x010F] = "SecretCamera"
    img.save(buf, "JPEG", exif=exif)
    out, _ = sanitise(buf.getvalue(), "photo", 5 * MB)
    assert b"SecretCamera" not in out


def test_rejections():
    with pytest.raises(UploadRejected):
        sanitise(b"", "photo", MB)
    with pytest.raises(UploadRejected):
        sanitise(png(), "photo", 100)  # too big
    with pytest.raises(UploadRejected):
        sanitise(b"<html><script>alert(1)</script></html>", "photo", MB)
    with pytest.raises(UploadRejected):
        sanitise(png(200, 150), "photo", MB)  # too small to read


def make_pdf() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(buf, "PDF")
    return buf.getvalue()


def test_pdf_only_for_certificate_and_without_active_content():
    clean_pdf = make_pdf()
    out, ext = sanitise(clean_pdf, "certificate", MB)
    assert ext == "pdf" and out == clean_pdf
    with pytest.raises(UploadRejected):
        sanitise(b"%PDF-1.4\n<< /OpenAction << /JS (app.alert(1)) >> >>", "certificate", MB)
    with pytest.raises(UploadRejected):
        sanitise(clean_pdf, "photo", MB)  # a PDF is not an image


def test_broken_pdf_rejected_when_pypdf_available():
    pytest.importorskip("pypdf")
    with pytest.raises(UploadRejected):
        sanitise(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF", "certificate", MB)
