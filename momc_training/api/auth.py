"""Applicant account endpoints: register, verify, login, logout, password reset.

Responses never reveal whether an email is registered (except to its owner,
by email). Every endpoint is rate limited per IP; logins are also limited
per email address.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import now_datetime

from momc_training.utils import mail, otp, passwords, security, session

_FAILS = "momc_ta:fails:{}"
MAX_FAILS = 5
LOCK_SECONDS = 15 * 60
GENERIC_SENT = "إذا كان البريد صحيحاً فقد أرسلنا إليه رمزاً مكوناً من 6 أرقام."


def _email(value: str) -> str:
    email = security.normalise_email(value)
    if not email:
        frappe.throw(_("أدخل بريداً إلكترونياً صحيحاً"))
    return email


def _applicant_by_email(email: str) -> dict | None:
    return frappe.db.get_value(
        "Training Applicant", {"email": email}, ["name", "email_verified", "status"], as_dict=True
    )


def _send_code(email: str, purpose: str) -> None:
    code = otp.issue(email, purpose)
    if code:
        mail.send_otp(email, code, purpose)


def _settings():
    return frappe.get_cached_doc("Training Program Settings")


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=3600)
def register(email: str, password: str, consent: int | str = 0):
    if not _settings().registration_open:
        frappe.throw(_("التسجيل مغلق حالياً"))
    email = _email(email)
    if str(consent) not in ("1", "true", "True"):
        frappe.throw(_("يجب الموافقة على سياسة استخدام البيانات"))
    problem = security.password_problem(password, email)
    if problem:
        frappe.throw(_(problem))

    existing = _applicant_by_email(email)
    if existing and existing.email_verified:
        mail.send_existing_account_notice(email)
    elif existing:
        # Unverified account: let the new password replace the old one.
        passwords.set_password(existing.name, password)
        _send_code(email, "verify")
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Training Applicant",
                "email": email,
                "status": "Draft",
                "consent": 1,
                "consent_on": now_datetime(),
            }
        )
        doc.insert(ignore_permissions=True)
        passwords.set_password(doc.name, password)
        _send_code(email, "verify")
    return {"message": GENERIC_SENT, "next": f"/training/verify?email={frappe.utils.quote(email)}"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def verify(email: str, code: str):
    email = _email(email)
    applicant = _applicant_by_email(email)
    if not applicant or not otp.check(email, "verify", code):
        frappe.throw(_("الرمز غير صحيح أو انتهت صلاحيته"))
    frappe.db.set_value(
        "Training Applicant", applicant.name, {"email_verified": 1, "last_login": now_datetime()},
        update_modified=False,
    )
    session.create(applicant.name)
    return {"next": "/training/profile"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=900)
def resend(email: str, purpose: str = "verify"):
    email = _email(email)
    if purpose not in otp.PURPOSES:
        frappe.throw(_("طلب غير صالح"))
    applicant = _applicant_by_email(email)
    if applicant and (purpose == "reset" or not applicant.email_verified):
        _send_code(email, purpose)
    return {"message": GENERIC_SENT}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=900)
def login(email: str, password: str):
    email = _email(email)
    fails_key = _FAILS.format(security.digest(frappe.utils.password.get_encryption_key(), "fails", email))
    fails = frappe.cache.get_value(fails_key, expires=True) or 0
    if fails >= MAX_FAILS:
        frappe.throw(_("تم إيقاف الدخول مؤقتاً بسبب محاولات خاطئة متكررة. حاول بعد 15 دقيقة."))

    applicant = _applicant_by_email(email)
    if not passwords.verify(applicant.name if applicant else None, password):
        frappe.cache.set_value(fails_key, fails + 1, expires_in_sec=LOCK_SECONDS)
        frappe.throw(_("البريد الإلكتروني أو كلمة المرور غير صحيحة"))

    frappe.cache.delete_value(fails_key)
    if not applicant.email_verified:
        _send_code(email, "verify")
        return {"next": f"/training/verify?email={frappe.utils.quote(email)}"}
    frappe.db.set_value("Training Applicant", applicant.name, "last_login", now_datetime(), update_modified=False)
    session.create(applicant.name)
    return {"next": "/training/status" if applicant.status != "Draft" else "/training/profile"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def logout():
    session.destroy()
    return {"next": "/training/login"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=900)
def forgot(email: str):
    email = _email(email)
    if _applicant_by_email(email):
        _send_code(email, "reset")
    return {"message": GENERIC_SENT, "next": f"/training/reset?email={frappe.utils.quote(email)}"}


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=20, seconds=3600)
def reset(email: str, code: str, password: str):
    email = _email(email)
    problem = security.password_problem(password, email)
    if problem:
        frappe.throw(_(problem))
    applicant = _applicant_by_email(email)
    if not applicant or not otp.check(email, "reset", code):
        frappe.throw(_("الرمز غير صحيح أو انتهت صلاحيته"))
    passwords.set_password(applicant.name, password)
    frappe.db.set_value("Training Applicant", applicant.name, "email_verified", 1, update_modified=False)
    session.destroy_all(applicant.name)
    return {"next": "/training/login", "message": "تم تغيير كلمة المرور، سجّل الدخول الآن."}
