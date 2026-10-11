"""Applicant passwords, stored with Frappe's own password machinery.

The hash lives in Frappe's __Auth table (pbkdf2 via passlib, the same path
as ERPNext user passwords), keyed by (Training Applicant, name, field). It is
never part of the document, so no REST call, report or export can return it.
"""

from __future__ import annotations

import frappe
from frappe.utils.password import check_password, remove_encrypted_password, update_password

from momc_training.utils import security

DOCTYPE = "Training Applicant"
FIELD = "portal_password"


def set_password(applicant: str, password: str) -> None:
    update_password(applicant, password, doctype=DOCTYPE, fieldname=FIELD)


def verify(applicant: str | None, password: str) -> bool:
    if not applicant:
        security.dummy_verify()
        return False
    try:
        check_password(applicant, password or "", doctype=DOCTYPE, fieldname=FIELD, delete_tracker_cache=False)
        return True
    except frappe.AuthenticationError:
        return False


def remove(applicant: str) -> None:
    remove_encrypted_password(DOCTYPE, applicant, fieldname=FIELD)
