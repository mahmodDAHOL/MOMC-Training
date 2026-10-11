import frappe
from frappe import _
from frappe.model.document import Document


class TrainingExamQuestion(Document):
    def validate(self):
        options = [self.option_a, self.option_b, self.option_c, self.option_d]
        if len({(o or "").strip() for o in options}) < 4:
            frappe.throw(_("يجب أن تكون الخيارات الأربعة مختلفة"))
        if (self.points or 0) <= 0:
            frappe.throw(_("علامة السؤال يجب أن تكون أكبر من صفر"))
