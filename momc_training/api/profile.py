"""Applicant profile: read, save (draft), submit."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from momc_training.ocr.text import clean, to_latin_digits
from momc_training.utils import mail, session

PROFILE_FIELDS = (
    "first_name", "father_name", "mother_name", "last_name", "national_id", "gender", "birth_date",
    "birth_place", "governorate", "registry", "address", "phone", "university", "faculty", "major",
    "graduation_year", "gpa", "track_preference",
)
REQUIRED = {
    "first_name": "الاسم", "father_name": "اسم الأب", "mother_name": "اسم ونسبة الأم", "last_name": "النسبة",
    "national_id": "الرقم الوطني", "gender": "الجنس", "birth_date": "تاريخ الولادة",
    "birth_place": "مكان الولادة", "phone": "رقم الهاتف", "university": "الجامعة", "major": "الاختصاص",
    "graduation_year": "سنة التخرج", "track_preference": "المسار المرغوب",
    "photo": "الصورة الشخصية", "id_front": "الهوية - الوجه الأمامي", "id_back": "الهوية - الوجه الخلفي",
    "certificate": "الشهادة",
}
# OCR result key -> form field, with the Arabic label used in the review note.
OCR_FIELDS = {
    "first_name": "الاسم", "last_name": "النسبة", "father_name": "اسم الأب", "mother_name": "اسم الأم",
    "birth_place": "مكان الولادة", "birth_date": "تاريخ الولادة", "national_id": "الرقم الوطني",
    "governorate": "الأمانة", "registry": "القيد",
}
FILES = ("photo", "id_front", "id_back", "certificate")


def _public(doc) -> dict:
    data = {f: doc.get(f) for f in PROFILE_FIELDS}
    if data.get("birth_date"):
        data["birth_date"] = str(data["birth_date"])
    data.update(
        name=doc.name, email=doc.email, status=doc.status, applicant_name=doc.applicant_name,
        files={f: bool(doc.get(f)) for f in FILES},
    )
    return data


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get():
    applicant = session.require(check_csrf=False)
    return _public(frappe.get_doc("Training Applicant", applicant))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def save(data: str | dict):
    applicant = session.require()
    values = json.loads(data) if isinstance(data, str) else data
    if not isinstance(values, dict):
        frappe.throw(_("بيانات غير صالحة"))
    doc = frappe.get_doc("Training Applicant", applicant)
    if doc.status != "Draft":
        frappe.throw(_("لا يمكن تعديل الطلب بعد إرساله"))
    for field in PROFILE_FIELDS:
        if field in values:
            value = values[field]
            if isinstance(value, str):
                value = clean(value)[:200]
            doc.set(field, value or None)
    if doc.national_id:
        doc.national_id = to_latin_digits(doc.national_id)
    doc.ocr_corrected_fields = _ocr_differences(doc)
    doc.save(ignore_permissions=True)
    return _public(doc)


def _ocr_differences(doc) -> str:
    raw = doc.ocr_data
    ocr = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
    read = {}
    for side in ocr.values():
        for key, item in side.items():
            if item.get("value"):
                read[key] = item["value"]
    changed = []
    for key, label in OCR_FIELDS.items():
        if key in read and doc.get(key) and clean(str(doc.get(key))) != clean(str(read[key])):
            changed.append(label)
    return "، ".join(changed)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit():
    applicant = session.require()
    doc = frappe.get_doc("Training Applicant", applicant)
    if doc.status != "Draft":
        frappe.throw(_("تم إرسال الطلب مسبقاً"))
    missing = [label for field, label in REQUIRED.items() if not doc.get(field)]
    if missing:
        frappe.throw(_("أكمل الحقول التالية قبل الإرسال: {0}").format("، ".join(missing)))
    doc.status = "Submitted"
    doc.submitted_on = now_datetime()
    doc.save(ignore_permissions=True)
    mail.send_submitted(doc)
    return {"next": "/training/exam"}
