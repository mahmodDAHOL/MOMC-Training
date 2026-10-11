"""Exam endpoints for the signed-in applicant."""

from __future__ import annotations

import frappe
from frappe.rate_limiter import rate_limit

from momc_training.exam import service
from momc_training.utils import session


@frappe.whitelist(allow_guest=True, methods=["POST"])
def start():
    applicant = session.require()
    attempt = service.start(
        applicant, ip=frappe.local.request_ip or "", user_agent=frappe.get_request_header("User-Agent") or ""
    )
    return service.payload(attempt)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def state():
    applicant = session.require(check_csrf=False)
    attempt = service.active_attempt(applicant)
    if not attempt:
        return {"status": "Not Started"}
    if attempt.status == "In Progress":
        attempt = service._expire_if_overdue(attempt)
    if attempt.status != "In Progress":
        return {"status": attempt.status}
    return service.payload(attempt)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=600, seconds=3600)
def answer(question: str, choice: int | str | None = None):
    applicant = session.require()
    return {"answered": service.save_answer(applicant, question, choice)}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def submit():
    applicant = session.require()
    service.submit(applicant)
    return {"next": "/training/status"}
