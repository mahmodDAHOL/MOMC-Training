import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from momc_training.exam import service
from momc_training.api import profile as profile_api
from momc_training.momc_training.doctype.training_applicant.training_applicant import decide
from momc_training.ocr.text import to_latin_digits


def make_applicant(email, **values):
    frappe.db.delete("Training Applicant", {"email": email})
    doc = frappe.get_doc({"doctype": "Training Applicant", "email": email, "status": "Draft", **values})
    doc.insert(ignore_permissions=True)
    return doc


def get_exam_domain():
    questions = frappe.get_all(
        "Training Exam Question",
        filters={"enabled": 1},
        pluck="section",
        order_by="section asc",
    )
    domains = set(frappe.get_all("Training Exam Domain", pluck="name"))
    return next(domain for domain in questions if domain in domains)


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

    def test_admission_profile_fields_are_saved_and_validated(self):
        doc = make_applicant(
            "admission-fields@test.sy",
            applicant_age=26,
            study_field="كلية الإعلام",
            education_status="خريج جامعي",
            current_employment="لا",
            english_level="جيد",
            full_time_available="نعم",
            has_laptop="نعم",
            ministry_interest="ربما",
            war_affected="لا",
            motivation="خبرة في الإعلام\nورغبة في خدمة الجمهور",
        )
        self.assertEqual(doc.applicant_age, 26)
        self.assertEqual(doc.study_field, "كلية الإعلام")
        self.assertEqual(doc.motivation, "خبرة في الإعلام\nورغبة في خدمة الجمهور")
        with self.assertRaises(frappe.ValidationError):
            make_applicant("invalid-study-field@test.sy", study_field="غير موجود")
        with self.assertRaises(frappe.ValidationError):
            make_applicant("invalid-age@test.sy", applicant_age=121)

    def test_non_it_profile_submission_skips_exam_and_track_requirement(self):
        values = {field: "value" for field in profile_api.REQUIRED}
        values.update(study_field="كلية الهندسة المعلوماتية", track_preference="Communications")
        doc = type(
            "Applicant",
            (),
            {
                **values,
                "name": "APP-TEST",
                "status": "Draft",
                "get": lambda self, field: values.get(field),
                "save": lambda self, **kwargs: None,
            },
        )()

        with patch.object(profile_api.session, "require", return_value=doc.name), \
             patch.object(profile_api.frappe, "get_doc", return_value=doc), \
             patch.object(profile_api.mail, "send_submitted"):
            result = profile_api.submit.__wrapped__(
                study_field="كلية الإعلام", track_preference=""
            )

        self.assertEqual(result["next"], "/training/status")
        self.assertEqual(doc.status, "Submitted")
        self.assertIsNone(doc.track_preference)

    def test_exam_expires_and_scores_saved_answers(self):
        domain = get_exam_domain()
        doc = make_applicant(
            "exam@test.sy", study_field="كلية الهندسة المعلوماتية", track_preference=domain
        )
        doc.db_set("status", "Submitted")
        attempt = service.start(doc.name)
        order = json.loads(attempt.question_order)
        sections = frappe.get_all(
            "Training Exam Question",
            filters={"name": ("in", [item["q"] for item in order])},
            pluck="section",
        )
        self.assertEqual(set(sections), {domain})
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

    def test_domain_only_exam_passes_at_half_of_available_points(self):
        doc = make_applicant(
            "domain-exam@test.sy",
            study_field="كلية الهندسة المعلوماتية",
            track_preference=get_exam_domain(),
        )
        doc.db_set("status", "Submitted")
        attempt = service.start(doc.name)
        order = json.loads(attempt.question_order)
        points = {
            row.name: row.points
            for row in frappe.get_all(
                "Training Exam Question",
                filters={"name": ("in", [item["q"] for item in order])},
                fields=["name", "points"],
            )
        }
        domain_max = sum(float(value or 0) for value in points.values())
        full_exam_max = sum(
            float(row.points or 0)
            for row in frappe.get_all("Training Exam Question", filters={"enabled": 1}, fields=["points"])
        )
        pass_score = (
            (frappe.get_cached_doc("Training Program Settings").pass_total or 50)
            * domain_max
            / full_exam_max
        )
        achieved = 0
        for item in order:
            correct = frappe.db.get_value("Training Exam Question", item["q"], "correct_option")
            shown = item["perm"].index("ABCD".index(correct))
            service.save_answer(doc.name, item["q"], shown)
            achieved += float(points[item["q"]] or 0)
            if achieved >= pass_score:
                break

        service.submit(doc.name)
        attempt.reload()
        self.assertEqual(attempt.max_score, domain_max)
        self.assertEqual(attempt.total_score, achieved)
        self.assertEqual(attempt.passed, 1)
        self.assertEqual(service.submit(doc.name).status, "Submitted")

    def test_answers_after_deadline_are_refused(self):
        doc = make_applicant(
            "late@test.sy",
            study_field="كلية الهندسة المعلوماتية",
            track_preference=get_exam_domain(),
        )
        doc.db_set("status", "Submitted")
        attempt = service.start(doc.name)
        attempt.db_set("deadline", add_to_date(now_datetime(), minutes=-2))
        q = json.loads(attempt.question_order)[0]["q"]
        with self.assertRaises(frappe.ValidationError):
            service.save_answer(doc.name, q, 0)
        self.assertEqual(frappe.db.get_value("Training Exam Attempt", attempt.name, "status"), "Expired")

    def test_non_it_applicant_does_not_start_exam(self):
        doc = make_applicant("no-exam@test.sy", study_field="كلية الإعلام")
        doc.db_set("status", "Submitted")

        with self.assertRaises(frappe.ValidationError):
            service.start(doc.name)

    def test_decide_accept_sets_track_and_status(self):
        frappe.flags.mute_emails = True
        domain = get_exam_domain()
        doc = make_applicant("decide@test.sy", track_preference=domain, first_name="ريم")
        doc.db_set("status", "Exam Completed")
        decide(doc.name, "Accepted", domain, "أهلاً بك")
        doc.reload()
        self.assertEqual((doc.status, doc.assigned_track), ("Accepted", domain))
        self.assertEqual(doc.decided_by, frappe.session.user)
        with self.assertRaises(frappe.ValidationError):
            decide(doc.name, "Maybe")
