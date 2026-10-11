"""Credential primitives for applicant accounts (pure; no Frappe imports).

Applicant passwords are stored by Frappe itself (frappe.utils.password, the
__Auth table) — see utils/passwords.py. This module holds the policy and the
random secrets: one-time codes and session tokens, whose only stored form is
a keyed SHA-256 digest, so a Redis dump reveals nothing usable.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

from passlib.context import CryptContext

# Same scheme Frappe uses; only to equalise timing for unknown accounts.
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

PASSWORD_MIN_LENGTH = 10
OTP_LENGTH = 6


def dummy_verify() -> None:
    """Spend the time of a real check (for unknown emails)."""
    _pwd.dummy_verify()


def password_problem(password: str, email: str = "") -> str | None:
    """Return an Arabic message describing why a password is weak, or None."""
    if len(password or "") < PASSWORD_MIN_LENGTH:
        return f"كلمة المرور يجب ألا تقل عن {PASSWORD_MIN_LENGTH} محارف"
    if len(password) > 128:
        return "كلمة المرور طويلة جداً"
    if not re.search(r"[A-Za-zء-ي]", password) or not re.search(r"\d", password):
        return "كلمة المرور يجب أن تحتوي على أحرف وأرقام"
    local = (email or "").split("@")[0].lower()
    if local and len(local) >= 4 and local in password.lower():
        return "كلمة المرور يجب ألا تحتوي على اسم البريد الإلكتروني"
    return None


def new_otp() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(OTP_LENGTH))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def digest(secret: str, *parts: str) -> str:
    """Keyed digest used as the storage form of codes and tokens."""
    msg = "\x1f".join(parts).encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def same(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")


EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def normalise_email(email: str) -> str:
    email = (email or "").strip().lower()
    return email if EMAIL_RE.match(email) and len(email) <= 140 else ""
