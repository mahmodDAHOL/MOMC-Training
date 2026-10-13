"""Upload sanitising (pure; Pillow only).

Images are decoded and re-encoded as JPEG: this drops EXIF (including GPS),
neutralises polyglot files, applies the camera orientation and caps size.
PDFs are accepted for document uploads by signature, with active content
(JavaScript / auto-actions / embedded files) rejected.
"""

from __future__ import annotations

import io
import re

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_SIDE = 2400
MAX_PIXELS = 40_000_000  # decompression-bomb guard
_PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|OpenAction|AA|Launch|EmbeddedFile|RichMedia|XFA)\b")
_PDF_KINDS = {"certificate", "cv", "work_sample", "recommendation_letter"}


class UploadRejected(ValueError):
    """The file is not acceptable; message is user-facing Arabic."""


def sanitise_image(data: bytes, max_side: int = MAX_SIDE) -> bytes:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        img = Image.open(io.BytesIO(data))
        if img.format not in ("JPEG", "PNG", "WEBP", "MPO"):
            raise UploadRejected("صيغة الصورة غير مدعومة. استخدم JPG أو PNG.")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError) as exc:
        raise UploadRejected("تعذّرت قراءة الصورة. تأكد أنها ملف صورة سليم.") from exc
    img = ImageOps.exif_transpose(img).convert("RGB")
    if min(img.size) < 300:
        raise UploadRejected("دقة الصورة منخفضة جداً. التقط صورة أوضح.")
    img.thumbnail((max_side, max_side), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=88, optimize=True)
    return out.getvalue()


def check_pdf(data: bytes) -> bytes:
    if not data.startswith(b"%PDF-"):
        raise UploadRejected("الملف ليس PDF صالحاً.")
    if _PDF_ACTIVE.search(data):
        raise UploadRejected("ملف PDF يحتوي على محتوى نشط غير مسموح. صدّره من جديد أو ارفع صورة.")
    try:
        from pypdf import PdfReader  # ships with Frappe

        if not PdfReader(io.BytesIO(data), strict=False).pages:
            raise UploadRejected("ملف PDF فارغ.")
    except ImportError:
        pass
    except UploadRejected:
        raise
    except Exception as exc:
        raise UploadRejected("ملف PDF تالف ولا يمكن فتحه. صدّره من جديد أو ارفع صورة.") from exc
    return data


def sanitise(data: bytes, kind: str, max_bytes: int) -> tuple[bytes, str]:
    """Return (clean bytes, extension) or raise UploadRejected."""
    if not data:
        raise UploadRejected("الملف فارغ.")
    if len(data) > max_bytes:
        raise UploadRejected(f"حجم الملف أكبر من المسموح ({max_bytes // (1024 * 1024)} ميغابايت).")
    if kind in _PDF_KINDS and data.startswith(b"%PDF-"):
        return check_pdf(data), "pdf"
    return sanitise_image(data), "jpg"
