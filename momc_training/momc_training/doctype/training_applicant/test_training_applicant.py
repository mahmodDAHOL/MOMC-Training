import json

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from momc_training.exam import service
from momc_training.momc_training.doctype.training_applicant.training_applicant import decide
from momc_training.ocr.text import to_latin_digits


def make_applicant(email, **values):
    frappe.db.delete("Training Applicant", {"email": email})
    doc = frappe.get_doc({"doctype": "Training Applicant", "email": email, "status": "Draft", **values})
    doc.insert(ignore_permissions=True)
    return doc


class TestTrainingApplicant(FrappeTestCase):
    def tearDown(self):
        frappe.db.rollback()

    def test_national_id_rules(self):
        frappe.db.delete("Training Applicant", {"national_id": to_latin_digits("٠١٢٣٤٥٦٧٨٩٠")})
        doc = make_applicant("nid@test.sy", national_id="٠١٢٣٤٥٦٧٨٩٠", first_name="سامر", last_name="علي")
        self.assertEqual(doc.national_id, "01234567890")
        self.assertEqual(doc.applicant_name, "سامر علي")
        with self.assertRaises(frappe.ValidationError):
            make_applicant("nid2@test.sy", national_id="01234567890")
        with self.assertRaises(frappe.ValidationError):
            make_applicant("nid3@test.sy", national_id="123")

    def test_exam_expires_and_scores_saved_answers(self):
        doc = make_applicant("exam@test.sy", track_preference="Programming")
        doc.db_set("status", "Submitted")
        attempt = service.start(doc.name)
        order = json.loads(attempt.question_order)
        first = order[0]
        correct = frappe.db.get_value("Training Exam Question", first["q"], "correct_option")
        shown = first["perm"].index("ABCD".index(correct))
        service.save_answer(doc.name, first["q"], shown)

        attempt.db_set("deadline", add_to_date(now_datetime(), minutes=-5))
        service.expire_overdue_attempts()

        attempt.reload()
        self.assertEqual(attempt.status, "Expired")
        points = frappe.db.get_value("Training Exam Question", first["q"], "points")
        self.assertEqual(attempt.total_score, points)
        self.assertEqual(frappe.db.get_value("Training Applicant", doc.name, "status"), "Exam Completed")
        with self.assertRaises(frappe.ValidationError):
            service.start(doc.name)

    def test_answers_after_deadline_are_refused(self):
        doc = make_applicant("late@test.sy")
        doc.db_set("status", "Submitted")
        attempt = service.start(doc.name)
        attempt.db_set("deadline", add_to_date(now_datetime(), minutes=-2))
        q = json.loads(attempt.question_order)[0]["q"]
        with self.assertRaises(frappe.ValidationError):
            service.save_answer(doc.name, q, 0)
        self.assertEqual(frappe.db.get_value("Training Exam Attempt", attempt.name, "status"), "Expired")

    def test_decide_accept_sets_track_and_status(self):
        frappe.flags.mute_emails = True
        doc = make_applicant("decide@test.sy", track_preference="Cybersecurity", first_name="ريم")
        doc.db_set("status", "Exam Completed")
        decide(doc.name, "Accepted", "Programming", "أهلاً بك")
        doc.reload()
        self.assertEqual((doc.status, doc.assigned_track), ("Accepted", "Programming"))
        self.assertEqual(doc.decided_by, frappe.session.user)
        with self.assertRaises(frappe.ValidationError):
            decide(doc.name, "Maybe")
