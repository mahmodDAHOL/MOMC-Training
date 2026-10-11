import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, getdate, now_datetime, nowdate

from momc_training.exam.scoring import TRACKS
from momc_training.ocr.text import clean, to_latin_digits, valid_national_id

DECISIONS = ("Accepted", "Rejected")


class TrainingApplicant(Document):
    def on_trash(self):
        from momc_training.utils import passwords, session

        passwords.remove(self.name)
        session.destroy_all(self.name)

    def validate(self):
        self.email = (self.email or "").strip().lower()
        if self.national_id:
            self.national_id = to_latin_digits(self.national_id).strip()
            if not valid_national_id(self.national_id):
                frappe.throw(_("الرقم الوطني يجب أن يتكون من 11 رقماً"))
            duplicate = frappe.db.get_value(
                "Training Applicant", {"national_id": self.national_id, "name": ("!=", self.name)}, "name"
            )
            if duplicate:
                frappe.throw(_("يوجد طلب آخر مسجل بهذا الرقم الوطني"))
        for field in ("first_name", "father_name", "mother_name", "last_name", "birth_place"):
            if self.get(field):
                self.set(field, clean(self.get(field)))
        self.applicant_name = " ".join(p for p in (self.first_name, self.father_name, self.last_name) if p) or self.email
        if self.birth_date and getdate(self.birth_date) > getdate(nowdate()):
            frappe.throw(_("تاريخ الولادة لا يمكن أن يكون في المستقبل"))
        if self.gpa and not 0 < flt(self.gpa) <= 100:
            frappe.throw(_("المعدل يجب أن يكون بين 0 و100"))
        if self.graduation_year and not 1980 <= cint(self.graduation_year) <= getdate(nowdate()).year + 1:
            frappe.throw(_("سنة التخرج غير صحيحة"))


@frappe.whitelist()
def decide(name: str, decision: str, track: str | None = None, notes: str | None = None):
    """Accept or reject an applicant from the desk (Training Manager only)."""
    frappe.only_for(("Training Manager", "System Manager"))
    if decision not in DECISIONS:
        frappe.throw(_("قرار غير صالح"))
    doc = frappe.get_doc("Training Applicant", name)
    doc.check_permission("write")
    if doc.status not in ("Submitted", "Exam Completed", "Accepted", "Rejected"):
        frappe.throw(_("لا يمكن اتخاذ قرار قبل إرسال الطلب"))
    if decision == "Accepted":
        track = track or doc.recommended_track or doc.track_preference
        if track not in TRACKS:
            frappe.throw(_("اختر المسار المعتمد"))
        doc.assigned_track = track
    doc.status = decision
    doc.decision_notes = notes
    doc.decided_by = frappe.session.user
    doc.decided_on = now_datetime()
    doc.save()

    from momc_training.utils.mail import send_decision

    send_decision(doc)
    return doc.status
