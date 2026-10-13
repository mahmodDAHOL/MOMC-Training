# Copyright (c) 2026, مديرية تقانة المعلومات والتحول الرقمي - وزارة الإعلام and Contributors
# See license.txt

from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from momc_training import install


class TestTrainingExamQuestion(FrappeTestCase):
    def test_ensure_exam_domains_creates_missing_domains(self):
        rows = [
            {"section": "Aptitude"},
            {"section": "Support"},
            {"section": "Aptitude"},
        ]
        with (
            patch.object(install, "_load", return_value=rows),
            patch.object(
                install.frappe.db,
                "exists",
                side_effect=lambda doctype, name: name == "Aptitude",
            ),
            patch.object(install.frappe, "get_doc") as get_doc,
        ):
            install._ensure_exam_domains()

        get_doc.assert_called_once_with(
            {"doctype": "Training Exam Domain", "exam_domain": "Support"}
        )
        get_doc.return_value.insert.assert_called_once_with(ignore_permissions=True)
