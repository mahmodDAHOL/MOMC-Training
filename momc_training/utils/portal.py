"""Shared context for the /training portal pages."""

from __future__ import annotations

import base64
import os
from functools import lru_cache

import frappe

from momc_training.utils.domains import get_track_ar
from momc_training.utils import session

STATUS_AR = {
    "Draft": "قيد الإعداد", "Submitted": "أُرسل الطلب", "Exam Completed": "أُنجز الامتحان",
    "Accepted": "مقبول", "Rejected": "لم يُقبل", "Withdrawn": "منسحب",
}


PUBLIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public")


@lru_cache(maxsize=8)
def _read(rel: str, mtime: float) -> str:
    with open(os.path.join(PUBLIC, rel), encoding="utf-8") as fh:
        return fh.read()


def _public_text(rel: str) -> str:
    """Portal CSS/JS, embedded in the page so it renders even when the
    /assets symlink is missing or stale (bench build not run, or a proxy
    that caches /assets). mtime in the cache key picks up edits."""
    path = os.path.join(PUBLIC, rel)
    return _read(rel, os.path.getmtime(path))


@lru_cache(maxsize=1)
def _logo_uri() -> str:
    with open(os.path.join(PUBLIC, "images", "momc-logo.png"), "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode()


def assets() -> dict:
    js = _public_text("js/portal.js").replace("</", "<\\/")  # cannot close the <script> tag early
    css = _public_text("css/portal.css").replace("</", "<\\/")
    return {"portal_css": css, "portal_js": js, "logo_uri": _logo_uri()}


def redirect(location: str):
    frappe.local.flags.redirect_location = location
    raise frappe.Redirect


def build(context, page: str, signed_in: bool | None = None):
    """signed_in=True: page needs a session; False: page is for guests only."""
    context.no_cache = 1
    context.page = page
    context.update(assets())
    settings = frappe.get_cached_doc("Training Program Settings")
    context.program_title = settings.program_title or "برنامج تدريب الخريجين الجدد"
    context.settings = settings
    context.track_ar = get_track_ar()
    context.domain_labels = context.track_ar
    context.status_ar = STATUS_AR
    data = session.current()
    context.csrf = data["csrf"] if data else ""
    context.applicant = None
    if data:
        context.applicant = frappe.db.get_value(
            "Training Applicant", data["applicant"],
            [
                "name",
                "email",
                "status",
                "first_name",
                "applicant_name",
                "exam_attempt",
                "track_preference",
            ],
            as_dict=True,
        )
        if not context.applicant:  # account removed from the desk
            session.destroy()
            data = None
    if signed_in is True and not data:
        redirect("/training/login")
    if signed_in is False and data:
        redirect(home_for(context.applicant.status))
    return context


def home_for(status: str) -> str:
    return "/training/profile" if status == "Draft" else "/training/status"
