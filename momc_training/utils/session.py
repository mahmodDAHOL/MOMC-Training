"""Applicant sessions, separate from Frappe users.

An applicant who signs in receives a random token in an httpOnly,
SameSite=Lax cookie. Redis stores only a keyed digest of that token, mapped
to {applicant, csrf}. State-changing API calls must also echo the CSRF token
in the X-TA-CSRF header (double defence alongside SameSite).
"""

from __future__ import annotations

import time

import frappe
from frappe import _
from frappe.utils.password import get_encryption_key

from momc_training.utils import security

COOKIE = "momc_ta_sid"
TTL = 8 * 3600  # sliding: refreshed on every authenticated request
_SESSION = "momc_ta:sess:{}"
_INDEX = "momc_ta:user:{}"


def _secret() -> str:
    return get_encryption_key()


def _key(token: str) -> str:
    return _SESSION.format(security.digest(_secret(), "session", token))


def create(applicant: str) -> dict:
    """Start a session for `applicant` and set the cookie."""
    token = security.new_token()
    data = {"applicant": applicant, "csrf": security.new_token(), "created": int(time.time())}
    key = _key(token)
    frappe.cache.set_value(key, data, expires_in_sec=TTL)
    frappe.cache.sadd(_INDEX.format(applicant), key)
    frappe.local.cookie_manager.set_cookie(COOKIE, token, max_age=TTL, httponly=True, samesite="Lax")
    frappe.local.momc_ta_session = data
    return data


def current() -> dict | None:
    """Session dict for this request, or None."""
    if hasattr(frappe.local, "momc_ta_session"):
        return frappe.local.momc_ta_session
    data = None
    token = frappe.request.cookies.get(COOKIE) if getattr(frappe, "request", None) else None
    if token and 20 <= len(token) <= 100:
        key = _key(token)
        data = frappe.cache.get_value(key, expires=True)
        if data:
            frappe.cache.expire(frappe.cache.make_key(key), TTL)
    frappe.local.momc_ta_session = data
    return data


def current_applicant() -> str | None:
    data = current()
    return data["applicant"] if data else None


def require(check_csrf: bool = True) -> str:
    """Return the signed-in applicant or stop the request with 401/403."""
    data = current()
    if not data:
        frappe.throw(_("انتهت الجلسة، يرجى تسجيل الدخول من جديد"), frappe.AuthenticationError)
    if check_csrf and frappe.request.method not in ("GET", "HEAD"):
        sent = frappe.get_request_header("X-TA-CSRF") or ""
        if not security.same(sent, data["csrf"]):
            frappe.throw(_("طلب غير صالح، أعد تحميل الصفحة"), frappe.CSRFTokenError)
    return data["applicant"]


def destroy() -> None:
    token = frappe.request.cookies.get(COOKIE) if getattr(frappe, "request", None) else None
    if token:
        key = _key(token)
        data = frappe.cache.get_value(key, expires=True)
        frappe.cache.delete_value(key)
        if data:
            frappe.cache.srem(_INDEX.format(data["applicant"]), key)
    frappe.local.cookie_manager.delete_cookie(COOKIE)
    frappe.local.momc_ta_session = None


def destroy_all(applicant: str) -> None:
    """Sign the applicant out everywhere (after a password change)."""
    index = _INDEX.format(applicant)
    keys = [k.decode() if isinstance(k, bytes) else k for k in frappe.cache.smembers(index) or []]
    if keys:
        frappe.cache.delete_value(keys)
    frappe.cache.delete_value(index)
