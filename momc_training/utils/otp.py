"""One-time email codes for account verification and password reset."""

from __future__ import annotations

import time

import frappe
from frappe.utils.password import get_encryption_key

from momc_training.utils import security

TTL = 15 * 60
MAX_ATTEMPTS = 5
RESEND_AFTER = 60
PURPOSES = ("verify", "reset")
_KEY = "momc_ta:otp:{}:{}"


def _key(purpose: str, email: str) -> str:
    return _KEY.format(purpose, security.digest(get_encryption_key(), "otp-id", email))


def issue(email: str, purpose: str) -> str | None:
    """Create a code; returns None while the resend cooldown is running."""
    assert purpose in PURPOSES
    key = _key(purpose, email)
    old = frappe.cache.get_value(key, expires=True)
    if old and time.time() - old["issued"] < RESEND_AFTER:
        return None
    code = security.new_otp()
    data = {"digest": security.digest(get_encryption_key(), purpose, email, code), "attempts": 0, "issued": time.time()}
    frappe.cache.set_value(key, data, expires_in_sec=TTL)
    return code


def check(email: str, purpose: str, code: str) -> bool:
    """Verify and consume a code. Wrong guesses are counted and capped."""
    key = _key(purpose, email)
    data = frappe.cache.get_value(key, expires=True)
    if not data or data["attempts"] >= MAX_ATTEMPTS:
        return False
    code = "".join(ch for ch in (code or "") if ch.isdigit())[: security.OTP_LENGTH]
    if security.same(data["digest"], security.digest(get_encryption_key(), purpose, email, code)):
        frappe.cache.delete_value(key)
        return True
    data["attempts"] += 1
    remaining = max(1, int(TTL - (time.time() - data["issued"])))
    frappe.cache.set_value(key, data, expires_in_sec=remaining)
    return False
