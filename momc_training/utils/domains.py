"""Training Exam Domain records used by the portal and applicant emails."""

from __future__ import annotations

import frappe


def get_track_ar() -> dict[str, str]:
    return {
        domain.name: domain.exam_domain
        for domain in frappe.get_all(
            "Training Exam Domain",
            fields=["name", "exam_domain"],
            order_by="name asc",
        )
    }


def get_domain_labels() -> dict[str, str]:
    return get_track_ar()
