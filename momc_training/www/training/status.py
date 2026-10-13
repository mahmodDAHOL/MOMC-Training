import frappe

from momc_training.utils.portal import build, redirect
from momc_training.utils.admission import requires_exam


def get_context(context):
    build(context, "status", signed_in=True)
    doc = frappe.get_doc("Training Applicant", context.applicant.name)
    if doc.status == "Draft":
        redirect("/training/profile")
    context.doc = doc
    context.requires_exam = requires_exam(doc.study_field)
    context.attempt = None
    if doc.exam_attempt and context.settings.show_score_to_applicant:
        context.attempt = frappe.db.get_value(
            "Training Exam Attempt", doc.exam_attempt,
            ["total_score", "max_score", "recommended_track", "status"],
            as_dict=True,
        )
    if context.requires_exam:
        order = ["Submitted", "Exam Completed", "Decision"]
        current = "Decision" if doc.status in ("Accepted", "Rejected") else doc.status
        context.stage = order.index(current) if current in order else 0
