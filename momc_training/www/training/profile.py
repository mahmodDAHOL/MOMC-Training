import frappe

from momc_training.api.profile import FILES, PROFILE_FIELDS
from momc_training.utils.admission import EXAM_STUDY_FIELD
from momc_training.utils.portal import build, redirect


def get_context(context):
    build(context, "profile", signed_in=True)
    if context.applicant.status != "Draft":
        redirect("/training/status")
    doc = frappe.get_doc("Training Applicant", context.applicant.name)
    context.v = {f: ("" if doc.get(f) is None else doc.get(f)) for f in PROFILE_FIELDS}
    context.files = {f: bool(doc.get(f)) for f in FILES}
    context.current_year = frappe.utils.getdate().year
    context.exam_study_field = EXAM_STUDY_FIELD
