"""Applicant profile: read, save (draft), submit."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from momc_training.ocr.text import clean, to_latin_digits
from momc_training.utils.admission import requires_exam
from momc_training.utils import mail, session

PROFILE_FIELDS = (
    "first_name", "father_name", "mother_name", "last_name", "national_id", "gender", "birth_date",
    "applicant_age", "birth_place", "governorate", "registry", "residence_city", "address", "phone",
    "university", "faculty", "major", "study_field", "study_field_other", "education_status",
    "graduate_specialty", "graduation_year", "gpa", "track_preference", "english_level", "other_languages",
    "current_employment", "current_job", "full_time_available", "part_time_available", "has_laptop",
    "ministry_interest", "motivation", "war_affected", "war_affected_details", "referral_name",
    "work_sample_description",
)
REQUIRED = {
    "first_name": "الاسم", "father_name": "اسم الأب", "mother_name": "اسم ونسبة الأم", "last_name": "النسبة",
    "national_id": "الرقم الوطني", "gender": "الجنس", "birth_date": "تاريخ الولادة",
    "birth_place": "مكان الولادة", "phone": "رقم الهاتف", "major": "الاختصاص",
    "graduation_year": "سنة التخرج",
    "applicant_age": "العمر", "residence_city": "مدينة الإقامة", "study_field": "مجال الدراسة",
    "education_status": "الحالة التعليمية", "current_employment": "الحالة الوظيفية",
    "english_level": "مستوى اللغة الإنجليزية", "full_time_available": "التفرغ للدوام الكامل",
    "has_laptop": "توفر حاسوب محمول", "ministry_interest": "الرغبة بالعمل في الوزارة",
    "motivation": "الدافع للعمل في الوزارة", "war_affected": "الإجابة عن حالة الإصابة أو الشهادة",
    "referral_name": "اسم الشخص الذي أوصى بالتدريب",
    "photo": "الصورة الشخصية", "id_front": "الهوية - الوجه الأمامي", "id_back": "الهوية - الوجه الخلفي",
    "certificate": "الشهادة", "cv": "السيرة الذاتية",
}
# OCR result key -> form field, with the Arabic label used in the review note.
OCR_FIELDS = {
    "first_name": "الاسم", "last_name": "النسبة", "father_name": "اسم الأب", "mother_name": "اسم الأم",
    "birth_place": "مكان الولادة", "birth_date": "تاريخ الولادة", "national_id": "الرقم الوطني",
    "governorate": "الأمانة", "registry": "القيد",
}
FILES = ("photo", "id_front", "id_back", "certificate", "cv", "work_sample", "recommendation_letter")


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
                if field == "applicant_age":
                    value = to_latin_digits(value).strip()
                    if not value.isdigit() or not 1 <= int(value) <= 120:
                        frappe.throw(_("العمر يجب أن يكون عدداً صحيحاً بين 1 و120"))
                if field == "motivation":
                    value = "\n".join(clean(line) for line in value.splitlines()).strip()[:3000]
                else:
                    value = clean(value)[:200]
            doc.set(field, value or None)
    if "study_field" in values and not requires_exam(doc.study_field):
        doc.track_preference = None
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
def submit(study_field: str | None = None, track_preference: str | None = None):
    applicant = session.require()
    doc = frappe.get_doc("Training Applicant", applicant)
    if doc.status != "Draft":
        frappe.throw(_("تم إرسال الطلب مسبقاً"))
    if study_field is not None:
        doc.study_field = clean(study_field)[:200] or None
    if track_preference is not None:
        doc.track_preference = clean(track_preference)[:200] or None
    if not requires_exam(doc.study_field):
        doc.track_preference = None
    missing = [label for field, label in REQUIRED.items() if not doc.get(field)]
    if requires_exam(doc.study_field) and not doc.track_preference:
        missing.append("المسار المرغوب")
    if doc.study_field == "خيارات أخرى" and not doc.study_field_other:
        missing.append("اسم مجال الدراسة")
    if missing:
        frappe.throw(_("أكمل الحقول التالية قبل الإرسال: {0}").format("، ".join(missing)))
    doc.status = "Submitted"
    doc.submitted_on = now_datetime()
    doc.save(ignore_permissions=True)
    mail.send_submitted(doc)
    return {"next": "/training/exam" if requires_exam(doc.study_field) else "/training/status"}
