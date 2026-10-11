import frappe

from momc_training.utils.portal import build, redirect


def get_context(context):
    build(context, "exam", signed_in=True)
    status = context.applicant.status
    if status == "Draft":
        redirect("/training/profile")
    attempt_status = None
    if context.applicant.exam_attempt:
        attempt_status = frappe.db.get_value("Training Exam Attempt", context.applicant.exam_attempt, "status")
    if attempt_status in ("Submitted", "Expired") or status in ("Exam Completed", "Accepted", "Rejected"):
        redirect("/training/status")
    context.in_progress = attempt_status == "In Progress"
    context.counts = {
        s: frappe.db.count("Training Exam Question", {"enabled": 1, "section": s})
        for s in ("Aptitude", "Support", "Security", "Programming")
    }
