"""Idempotent setup: role, number cards, default settings, question bank."""

import json
import os

import frappe

DATA = os.path.join(os.path.dirname(__file__), "data")
ROLE = "Training Manager"


def after_install():
    after_migrate()


def after_migrate():
    _ensure_role()
    _ensure_number_cards()
    _ensure_settings()
    _ensure_exam_domains()
    _seed_questions()


def _load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def _ensure_role():
    if not frappe.db.exists("Role", ROLE):
        frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 1}).insert(ignore_permissions=True)


def _ensure_number_cards():
    for card in _load("number_cards.json"):
        if frappe.db.exists("Number Card", card["name"]):
            # Keep the approved identity colours current on existing sites.
            frappe.db.set_value("Number Card", card["name"], "color", card["color"], update_modified=False)
            continue
        doc = frappe.get_doc({"doctype": "Number Card", "module": "MOMC Training", "is_standard": 0, **card})
        doc.insert(ignore_permissions=True, set_name=card["name"])


def _ensure_settings():
    settings = frappe.get_single("Training Program Settings")
    if not settings.exam_duration_minutes:
        meta = frappe.get_meta("Training Program Settings")
        for df in meta.fields:
            if df.default and settings.get(df.fieldname) in (None, "", 0):
                settings.set(df.fieldname, df.default)
        settings.flags.ignore_permissions = True
        settings.save()


def _ensure_exam_domains():
    """Create the domain records referenced by the bundled question bank."""
    sections = {row["section"] for row in _load("exam_questions.json") if row.get("section")}
    for section in sorted(sections):
        if not frappe.db.exists("Training Exam Domain", section):
            frappe.get_doc(
                {"doctype": "Training Exam Domain", "exam_domain": section}
            ).insert(ignore_permissions=True)


def _seed_questions():
    """Load the programme's 50 questions once; never overwrite edits."""
    if frappe.db.count("Training Exam Question"):
        return
    for row in _load("exam_questions.json"):
        frappe.get_doc({"doctype": "Training Exam Question", "enabled": 1, **row}).insert(ignore_permissions=True)
