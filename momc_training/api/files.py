"""Applicant uploads: profile documents, photo and both sides of the national ID.

Files are stored as *private* Frappe File records attached to the applicant,
so desk users see them on the form and nobody else can fetch them. The
applicant views their own files through `view`, which checks the session.
Uploading an ID side also runs OCR and returns suggested field values.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from momc_training.utils import session
from momc_training.utils.uploads import UploadRejected, sanitise

KINDS = {
    "photo": "الصورة الشخصية",
    "id_front": "الهوية - الوجه الأمامي",
    "id_back": "الهوية - الوجه الخلفي",
    "certificate": "الشهادة",
    "cv": "السيرة الذاتية",
    "work_sample": "نموذج العمل",
    "recommendation_letter": "رسالة التوصية",
}
OCR_SIDE = {"id_front": "front", "id_back": "back"}
GENDER_VALUE = {"ذكر": "Male", "أنثى": "Female"}


def _editable(applicant: str):
    doc = frappe.get_doc("Training Applicant", applicant)
    if doc.status != "Draft":
        frappe.throw(_("لا يمكن تعديل الطلب بعد إرساله"))
    return doc


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=60, seconds=3600)
def upload(kind: str):
    applicant = session.require()
    if kind not in KINDS:
        frappe.throw(_("نوع ملف غير معروف"))
    upload_file = frappe.request.files.get("file")
    if not upload_file:
        frappe.throw(_("لم يصل أي ملف"))
    max_mb = frappe.get_cached_doc("Training Program Settings").max_upload_mb or 5
    raw = upload_file.stream.read(max_mb * 1024 * 1024 + 1)
    try:
        content, ext = sanitise(raw, kind, max_mb * 1024 * 1024)
    except UploadRejected as exc:
        frappe.throw(str(exc))

    doc = _editable(applicant)
    _replace_file(doc, kind, content, ext)
    
    result = {"kind": kind, "uploaded": True}
    if kind in OCR_SIDE:
        result["ocr"] = _run_ocr(doc, kind, content)
    return result


def _replace_file(doc, kind: str, content: bytes, ext: str) -> None:
    for old in frappe.get_all(
        "File",
        filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "attached_to_field": kind},
        pluck="name",
    ):
        frappe.delete_doc("File", old, ignore_permissions=True)
    file_doc = frappe.get_doc(
        {
            "doctype": "File",
            "file_name": f"{doc.name}-{kind}.{ext}",
            "attached_to_doctype": doc.doctype,
            "attached_to_name": doc.name,
            "attached_to_field": kind,
            "is_private": 1,
            "content": content,
        }
    ).insert(ignore_permissions=True)
    doc.db_set(kind, file_doc.file_url, update_modified=True)


def _run_ocr(doc, kind: str, content: bytes) -> dict:
    from momc_training.ocr.syrian_id import OCRUnavailable, read_card

    try:
        result = read_card(content, side=OCR_SIDE[kind])
    except OCRUnavailable:
        frappe.log_error(title="OCR unavailable", message=frappe.get_traceback())
        return {"status": "unavailable"}
    except Exception:
        frappe.log_error(title="OCR failed", message=frappe.get_traceback())
        return {"status": "failed"}
    stored = json.loads(doc.ocr_data) if isinstance(doc.ocr_data, str) and doc.ocr_data else (doc.ocr_data or {})
    stored[result["side"]] = result["fields"]
    doc.db_set("ocr_data", json.dumps(stored, ensure_ascii=False), update_modified=False)
    found = {k: v["value"] for k, v in result["fields"].items() if v["value"]}
    if "gender" in found:
        found["gender"] = GENDER_VALUE.get(found["gender"], "")
    confidence = {k: v["confidence"] for k, v in result["fields"].items()}
    if "birth" in confidence:  # internal row name, not a form field
        confidence.pop("birth")
    return {"status": "ok", "side": result["side"], "fields": found, "confidence": confidence}


@frappe.whitelist(allow_guest=True, methods=["GET"])
def view(kind: str):
    """Stream one of the signed-in applicant's own files."""
    applicant = session.require(check_csrf=False)
    if kind not in KINDS:
        frappe.throw(_("نوع ملف غير معروف"))
    name = frappe.db.get_value(
        "File",
        {"attached_to_doctype": "Training Applicant", "attached_to_name": applicant, "attached_to_field": kind},
        "name",
    )
    if not name:
        raise frappe.DoesNotExistError
    file_doc = frappe.get_doc("File", name)
    frappe.local.response.filename = file_doc.file_name
    frappe.local.response.filecontent = file_doc.get_content()
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"
