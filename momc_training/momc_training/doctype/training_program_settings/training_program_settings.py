import frappe
from frappe import _
from frappe.model.document import Document


class TrainingProgramSettings(Document):
    def validate(self):
        if (self.exam_duration_minutes or 0) < 5:
            frappe.throw(_("مدة الامتحان يجب ألا تقل عن 5 دقائق"))
        if not 1 <= (self.max_upload_mb or 0) <= 20:
            frappe.throw(_("الحجم الأقصى للملف بين 1 و20 ميغابايت"))


def get_settings():
    return frappe.get_cached_doc("Training Program Settings")
