"""Exam lifecycle: start, serve questions, record answers, score, expire.

Correct answers never leave the server. Each attempt stores its own question
order and a per-question option permutation, so two applicants side by side
see different orders, and answers are mapped back to the bank's letters
before scoring.
"""

from __future__ import annotations

import json
import random
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from momc_training.exam.scoring import SECTIONS, Rules, score

LETTERS = "ABCD"
GRACE_SECONDS = 30  # network latency allowance at the deadline


def _settings():
    return frappe.get_cached_doc("Training Program Settings")


def _loads(value, default):
    if not value:
        return default
    return json.loads(value) if isinstance(value, str) else value


def active_attempt(applicant: str):
    name = frappe.db.get_value(
        "Training Exam Attempt", {"applicant": applicant}, "name", order_by="creation desc"
    )
    return frappe.get_doc("Training Exam Attempt", name, for_update=True) if name else None


def start(applicant: str, ip: str = "", user_agent: str = ""):
    settings = _settings()
    if not settings.exam_open:
        frappe.throw(_("الامتحان غير متاح حالياً"))
    status = frappe.db.get_value("Training Applicant", applicant, "status")
    existing = active_attempt(applicant)
    if existing:
        if existing.status == "In Progress":
            return _expire_if_overdue(existing)
        frappe.throw(_("لقد أدّيت الامتحان مسبقاً"))
    if status != "Submitted":
        frappe.throw(_("أرسل طلبك المكتمل أولاً، ثم ابدأ الامتحان"))

    rng = random.SystemRandom()
    order = []
    for section in SECTIONS:
        names = frappe.get_all(
            "Training Exam Question", filters={"enabled": 1, "section": section}, pluck="name", order_by="name asc"
        )
        if settings.shuffle_questions:
            rng.shuffle(names)
        for name in names:
            perm = list(range(4))
            if settings.shuffle_questions:
                rng.shuffle(perm)
            order.append({"q": name, "perm": perm})
    if not order:
        frappe.throw(_("لا توجد أسئلة مفعّلة في بنك الأسئلة"))

    started = now_datetime()
    attempt = frappe.get_doc(
        {
            "doctype": "Training Exam Attempt",
            "applicant": applicant,
            "status": "In Progress",
            "started_at": started,
            "deadline": add_to_date(started, minutes=settings.exam_duration_minutes or 90),
            "question_order": json.dumps(order),
            "answers": json.dumps({}),
            "ip_address": (ip or "")[:140],
            "user_agent": (user_agent or "")[:500],
        }
    ).insert(ignore_permissions=True)
    frappe.db.set_value("Training Applicant", applicant, "exam_attempt", attempt.name, update_modified=False)
    return attempt


def payload(attempt) -> dict:
    """What the browser needs: questions with shuffled options, saved picks, time left."""
    order = _loads(attempt.question_order, [])
    answers = _loads(attempt.answers, {})
    names = [item["q"] for item in order]
    rows = {
        r.name: r
        for r in frappe.get_all(
            "Training Exam Question",
            filters={"name": ("in", names)},
            fields=["name", "section", "question", "option_a", "option_b", "option_c", "option_d"],
        )
    }
    questions = []
    for item in order:
        row = rows.get(item["q"])
        if not row:
            continue
        original = [row.option_a, row.option_b, row.option_c, row.option_d]
        picked = answers.get(item["q"])
        shown_pick = item["perm"].index(LETTERS.index(picked)) if picked in tuple(LETTERS) else None
        questions.append(
            {
                "id": row.name,
                "section": row.section,
                "text": row.question,
                "options": [original[i] for i in item["perm"]],
                "picked": shown_pick,
            }
        )
    left = (get_datetime(attempt.deadline) - now_datetime()).total_seconds()
    return {"attempt": attempt.name, "status": attempt.status, "seconds_left": max(0, int(left)), "questions": questions}


def save_answer(applicant: str, question: str, shown_index: int | None):
    attempt = active_attempt(applicant)
    if not attempt or attempt.status != "In Progress":
        frappe.throw(_("لا يوجد امتحان جارٍ"))
    if now_datetime() > get_datetime(attempt.deadline) + timedelta(seconds=GRACE_SECONDS):
        finalize(attempt, "Expired")
        frappe.db.commit()  # keep the hand-in; the throw below would roll it back
        frappe.throw(_("انتهى وقت الامتحان وتم تسليم إجاباتك المحفوظة"))
    order = {item["q"]: item["perm"] for item in _loads(attempt.question_order, [])}
    if question not in order:
        frappe.throw(_("سؤال غير معروف"))
    answers = _loads(attempt.answers, {})
    if shown_index is None or shown_index == "":
        answers.pop(question, None)
    else:
        shown_index = int(shown_index)
        if not 0 <= shown_index < 4:
            frappe.throw(_("خيار غير صالح"))
        answers[question] = LETTERS[order[question][shown_index]]
    attempt.db_set("answers", json.dumps(answers), update_modified=False)
    return len(answers)


def submit(applicant: str):
    attempt = active_attempt(applicant)
    if not attempt or attempt.status != "In Progress":
        frappe.throw(_("لا يوجد امتحان جارٍ"))
    late = now_datetime() > get_datetime(attempt.deadline) + timedelta(seconds=GRACE_SECONDS)
    return finalize(attempt, "Expired" if late else "Submitted")


def _expire_if_overdue(attempt):
    if now_datetime() > get_datetime(attempt.deadline) + timedelta(seconds=GRACE_SECONDS):
        finalize(attempt, "Expired")
    return attempt


def finalize(attempt, status: str):
    """Score the attempt from saved answers and update the applicant."""
    settings = _settings()
    order = _loads(attempt.question_order, [])
    answers = _loads(attempt.answers, {})
    bank = frappe.get_all(
        "Training Exam Question",
        filters={"name": ("in", [i["q"] for i in order])},
        fields=["name", "section", "correct_option as correct", "points"],
    )
    preference = frappe.db.get_value("Training Applicant", attempt.applicant, "track_preference") or ""
    rules = Rules(settings.pass_total or 50, settings.pass_aptitude or 20, settings.track_min or 10)
    result = score([dict(r) for r in bank], answers, preference, rules)

    attempt.update(
        {
            "status": status,
            "submitted_at": now_datetime(),
            "total_score": result.total,
            "max_score": result.max_total,
            "passed": int(result.passed),
            "recommended_track": result.recommended_track,
            "score_aptitude": result.by_section["Aptitude"],
            "score_support": result.by_section["Support"],
            "score_security": result.by_section["Security"],
            "score_programming": result.by_section["Programming"],
        }
    )
    attempt.save(ignore_permissions=True)
    frappe.db.set_value(
        "Training Applicant",
        attempt.applicant,
        {
            "status": "Exam Completed",
            "exam_attempt": attempt.name,
            "exam_total": result.total,
            "exam_passed": int(result.passed),
            "recommended_track": result.recommended_track,
        },
    )
    return attempt


def expire_overdue_attempts():
    """Scheduler: close attempts whose time ran out with the browser closed."""
    cutoff = now_datetime() - timedelta(seconds=GRACE_SECONDS)
    for name in frappe.get_all(
        "Training Exam Attempt", filters={"status": "In Progress", "deadline": ("<", cutoff)}, pluck="name"
    ):
        finalize(frappe.get_doc("Training Exam Attempt", name, for_update=True), "Expired")
        frappe.db.commit()  # one attempt per transaction so one failure doesn't block the rest
