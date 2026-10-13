"""Applicant emails (Arabic, RTL, branded)."""

from __future__ import annotations

import frappe
from frappe.utils import escape_html, get_url

from momc_training.utils.domains import get_track_ar

TEAL = "#126E70"
DEEP = "#054239"
SAND = "#988561"


def _layout(title: str, body_html: str) -> str:
    program = escape_html(frappe.db.get_single_value("Training Program Settings", "program_title") or "")
    return f"""
<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;background:#f4f1ec;padding:24px">
  <div style="max-width:560px;margin:auto;background:#fff;border-radius:12px;overflow:hidden;border:1px solid #e6e0d6">
    <div style="background:{DEEP};color:#fff;padding:18px 24px;font-size:18px;font-weight:bold;border-bottom:4px solid {SAND}">{program}</div>
    <div style="padding:24px;color:#1f2a2a;line-height:1.9;font-size:15px">
      <h2 style="margin:0 0 12px;color:{TEAL};font-size:19px">{title}</h2>
      {body_html}
    </div>
    <div style="border-top:3px solid {SAND};padding:12px 24px;color:#6b6b6b;font-size:12px">
      وزارة الإعلام — مديرية تقانة المعلومات والتحول الرقمي
    </div>
  </div>
</div>"""


def _send(recipient: str, subject: str, html: str, now: bool = False) -> None:
    frappe.sendmail(recipients=[recipient], subject=subject, message=html, delayed=not now, now=now)


def send_otp(email: str, code: str, purpose: str) -> None:
    what = "تأكيد بريدك الإلكتروني" if purpose == "verify" else "إعادة تعيين كلمة المرور"
    body = f"""<p>رمز {what}:</p>
<p style="font-size:30px;letter-spacing:8px;font-weight:bold;color:{TEAL};direction:ltr;text-align:center">{code}</p>
<p>الرمز صالح لمدة 15 دقيقة. إن لم تطلب هذا الرمز فتجاهل هذه الرسالة.</p>"""
    _send(email, f"رمز {what}: {code}", _layout(what, body))


def send_existing_account_notice(email: str) -> None:
    link = get_url("/training/login")
    body = f"""<p>حاول أحدهم إنشاء حساب جديد بهذا البريد، لكن لديك حساباً مسجلاً بالفعل.</p>
<p>يمكنك <a href="{link}">تسجيل الدخول من هنا</a>، أو استعادة كلمة المرور إن نسيتها.</p>"""
    _send(email, "لديك حساب مسجل بالفعل", _layout("لديك حساب مسجل", body))


def send_submitted(doc) -> None:
    from momc_training.utils.admission import requires_exam

    if requires_exam(doc.study_field):
        link = get_url("/training/exam")
        body = f"""<p>مرحباً {escape_html(doc.first_name or '')}،</p>
<p>استلمنا طلبك ورقمه <b dir="ltr">{doc.name}</b>. الخطوة التالية هي امتحان القبول.</p>
<p><a href="{link}" style="background:{TEAL};color:#fff;padding:10px 18px;border-radius:8px;text-decoration:none">الانتقال إلى الامتحان</a></p>"""
    else:
        link = get_url("/training/status")
        body = f"""<p>مرحباً {escape_html(doc.first_name or '')}،</p>
<p>استلمنا معلومات طلبك ورقمه <b dir="ltr">{doc.name}</b>. لا يتطلب التقديم في مجال دراستك امتحاناً، وستتم مراجعة معلوماتك من قبل اللجنة.</p>
<p><a href="{link}">متابعة حالة الطلب</a></p>"""
    _send(doc.email, "تم استلام طلبك", _layout("تم استلام طلبك", body))


def send_decision(doc) -> None:
    notes = f"<p>{escape_html(doc.decision_notes)}</p>" if doc.decision_notes else ""
    if doc.status == "Accepted":
        track = get_track_ar().get(doc.assigned_track, doc.assigned_track or "")
        body = f"""<p>مرحباً {escape_html(doc.first_name or '')}،</p>
<p>يسرّنا إبلاغك بقبولك في البرنامج التدريبي ضمن مسار <b>{escape_html(track)}</b>.</p>{notes}
<p>سنتواصل معك قريباً بموعد البدء.</p>"""
        _send(doc.email, "تهانينا — تم قبولك في البرنامج التدريبي", _layout("تم قبولك", body))
    else:
        body = f"""<p>مرحباً {escape_html(doc.first_name or '')}،</p>
<p>نشكرك على اهتمامك بالبرنامج. نعتذر عن عدم إمكانية قبول طلبك في هذه الدورة.</p>{notes}"""
        _send(doc.email, "نتيجة طلب الانضمام إلى البرنامج التدريبي", _layout("نتيجة الطلب", body))
