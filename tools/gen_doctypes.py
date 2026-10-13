"""Generate the app's DocType JSON files (run once; output is committed).

Keeping the schema here as plain Python makes it reviewable in one place.
"""
import json
import os

MODULE = "MOMC Training"
BASE = os.path.join(os.path.dirname(__file__), "..", "momc_training", "momc_training", "doctype")
STAMP = "2026-10-11 09:00:00.000000"

def F(fieldname, fieldtype, label=None, **kw):
    d = {"fieldname": fieldname, "fieldtype": fieldtype}
    if label:
        d["label"] = label
    d.update(kw)
    return d

def SB(name, label=None, **kw): return F(name, "Section Break", label, **kw)
def CB(name): return F(name, "Column Break")

def perm(role, **kw):
    base = {"role": role, "read": 1, "report": 1, "export": 1, "print": 1, "email": 1, "share": 1}
    base.update(kw)
    return base

def write(name, fields, permissions, **meta):
    folder = os.path.join(BASE, name.lower().replace(" ", "_"))
    os.makedirs(folder, exist_ok=True)
    doc = {
        "actions": [], "creation": STAMP, "doctype": "DocType", "engine": "InnoDB",
        "field_order": [f["fieldname"] for f in fields], "fields": fields,
        "index_web_pages_for_search": 0, "links": [], "modified": STAMP,
        "modified_by": "Administrator", "module": MODULE, "name": name, "owner": "Administrator",
        "permissions": permissions, "sort_field": "creation", "sort_order": "DESC", "states": [],
    }
    doc.update(meta)
    with open(os.path.join(folder, folder.rsplit(os.sep, 1)[1] + ".json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    open(os.path.join(folder, "__init__.py"), "a").close()
    return folder

applicant = [
    SB("account_section", "الحساب"),
    F("applicant_name", "Data", "الاسم الكامل", read_only=1, in_list_view=1, in_global_search=1),
    F("email", "Data", "البريد الإلكتروني", options="Email", reqd=1, unique=1, in_global_search=1, search_index=1),
    F("phone", "Data", "رقم الهاتف", options="Phone"),
    CB("account_col"),
    F("status", "Select", "الحالة", options="Draft\nSubmitted\nExam Completed\nAccepted\nRejected\nWithdrawn",
      default="Draft", in_list_view=1, in_standard_filter=1, read_only=1, search_index=1),
    F("email_verified", "Check", "البريد مؤكَّد", read_only=1),
    F("submitted_on", "Datetime", "تاريخ إرسال الطلب", read_only=1),
    F("last_login", "Datetime", "آخر دخول", read_only=1),

    SB("personal_section", "البيانات الشخصية (حسب الهوية)"),
    F("first_name", "Data", "الاسم"),
    F("father_name", "Data", "اسم الأب"),
    F("mother_name", "Data", "اسم ونسبة الأم"),
    F("last_name", "Data", "النسبة"),
    CB("personal_col"),
    F("national_id", "Data", "الرقم الوطني", length=11, in_standard_filter=1, in_global_search=1, search_index=1, no_copy=1),
    F("gender", "Select", "الجنس", options="\nMale\nFemale"),
    F("birth_date", "Date", "تاريخ الولادة"),
    F("birth_place", "Data", "مكان الولادة"),
    SB("address_section"),
    F("governorate", "Data", "الأمانة"),
    F("registry", "Data", "القيد"),
    CB("address_col"),
    F("address", "Small Text", "العنوان الحالي"),

    SB("education_section", "المؤهل العلمي والمسار"),
    F("university", "Data", "الجامعة"),
    F("faculty", "Data", "الكلية"),
    F("major", "Data", "الاختصاص"),
    CB("education_col"),
    F("graduation_year", "Int", "سنة التخرج"),
    F("gpa", "Float", "المعدل", precision="2"),
    F("track_preference", "Link", "المسار المرغوب", options="Training Exam Domain", in_list_view=1, in_standard_filter=1),

    SB("files_section", "المرفقات"),
    F("photo", "Attach Image", "الصورة الشخصية"),
    F("certificate", "Attach", "الشهادة الجامعية"),
    CB("files_col"),
    F("id_front", "Attach Image", "صورة الهوية - الوجه الأمامي"),
    F("id_back", "Attach Image", "صورة الهوية - الوجه الخلفي"),

    SB("ocr_section", "قراءة الهوية آلياً", collapsible=1),
    F("ocr_corrected_fields", "Small Text", "حقول عدّلها المتقدم بعد القراءة الآلية", read_only=1,
      description="الحقول التي غيّر المتقدم قيمتها عمّا قرأه النظام من الهوية — تستحق التدقيق."),
    CB("ocr_col"),
    F("ocr_data", "JSON", "نتيجة القراءة الآلية", read_only=1),

    SB("exam_section", "الامتحان والقرار"),
    F("exam_attempt", "Link", "محاولة الامتحان", options="Training Exam Attempt", read_only=1),
    F("exam_total", "Float", "علامة الامتحان", read_only=1, in_list_view=1),
    F("exam_passed", "Check", "تجاوز الحد الأدنى", read_only=1),
    F("recommended_track", "Link", "المسار المقترح آلياً", options="Training Exam Domain", read_only=1),
    CB("decision_col"),
    F("assigned_track", "Link", "المسار المعتمد", options="Training Exam Domain", read_only=1, in_standard_filter=1),
    F("decision_notes", "Small Text", "ملاحظات القرار", read_only=1),
    F("decided_by", "Link", "صاحب القرار", options="User", read_only=1),
    F("decided_on", "Datetime", "تاريخ القرار", read_only=1),

    SB("consent_section", "الموافقة", collapsible=1),
    F("consent", "Check", "وافق على سياسة استخدام البيانات", read_only=1),
    F("consent_on", "Datetime", "تاريخ الموافقة", read_only=1),
]
write("Training Applicant", applicant,
      [perm("System Manager", write=1, delete=1), perm("Training Manager", write=1)],
      autoname="format:TA-{YYYY}-{#####}", naming_rule="Expression", title_field="applicant_name",
      show_title_field_in_link=1, image_field="photo", search_fields="email,national_id",
      track_changes=1, show_preview_popup=1)

question = [
    F("section", "Link", "القسم", options="Training Exam Domain", reqd=1,
      in_list_view=1, in_standard_filter=1),
    F("enabled", "Check", "مفعّل", default="1", in_list_view=1),
    F("points", "Float", "العلامة", default="2", reqd=1),
    F("question", "Small Text", "السؤال", reqd=1, in_list_view=1),
    SB("options_section", "الخيارات"),
    F("option_a", "Data", "الخيار أ", reqd=1),
    F("option_b", "Data", "الخيار ب", reqd=1),
    CB("options_col"),
    F("option_c", "Data", "الخيار ج", reqd=1),
    F("option_d", "Data", "الخيار د", reqd=1),
    SB("answer_section", "الإجابة"),
    F("correct_option", "Select", "الإجابة الصحيحة", options="A\nB\nC\nD", reqd=1),
    F("explanation", "Small Text", "التعليل (للمصحّح فقط)"),
]
write("Training Exam Question", question,
      [perm("System Manager", write=1, create=1, delete=1, import_=1), perm("Training Manager", write=1, create=1, delete=1)],
      autoname="format:Q-{#####}", naming_rule="Expression", title_field="question", sort_field="name", sort_order="ASC")

attempt = [
    F("applicant", "Link", "المتقدم", options="Training Applicant", reqd=1, in_list_view=1, search_index=1),
    F("applicant_name", "Data", "الاسم", fetch_from="applicant.applicant_name", read_only=1, in_list_view=1),
    F("status", "Select", "الحالة", options="In Progress\nSubmitted\nExpired", default="In Progress",
      in_list_view=1, in_standard_filter=1),
    CB("time_col"),
    F("started_at", "Datetime", "وقت البدء"),
    F("deadline", "Datetime", "الموعد النهائي"),
    F("submitted_at", "Datetime", "وقت التسليم"),
    SB("result_section", "النتيجة"),
    F("total_score", "Float", "المجموع", in_list_view=1),
    F("max_score", "Float", "العلامة العظمى"),
    F("passed", "Check", "تجاوز الحد الأدنى", in_standard_filter=1),
    F("recommended_track", "Link", "المسار المقترح", options="Training Exam Domain"),
    CB("result_col"),
    SB("data_section", "البيانات الخام", collapsible=1),
    F("question_order", "JSON", "ترتيب الأسئلة"),
    F("answers", "JSON", "الإجابات"),
    F("ip_address", "Data", "عنوان IP"),
    F("user_agent", "Small Text", "المتصفح"),
]
for f in attempt:
    if f["fieldtype"] not in ("Section Break", "Column Break"):
        f["read_only"] = 1
write("Training Exam Attempt", attempt,
      [perm("System Manager", delete=1), perm("Training Manager")],
      autoname="format:EX-{YYYY}-{#####}", naming_rule="Expression", title_field="applicant_name", in_create=1)

settings = [
    SB("general_section", "عام"),
    F("program_title", "Data", "اسم البرنامج", default="برنامج تدريب الخريجين الجدد"),
    F("registration_open", "Check", "التسجيل مفتوح", default="1"),
    F("exam_open", "Check", "الامتحان متاح", default="1"),
    CB("general_col"),
    F("contact_email", "Data", "بريد التواصل", options="Email"),
    F("max_upload_mb", "Int", "الحجم الأقصى للملف (MB)", default="5"),
    SB("exam_section", "الامتحان"),
    F("exam_duration_minutes", "Int", "مدة الامتحان (دقيقة)", default="90"),
    F("shuffle_questions", "Check", "خلط ترتيب الأسئلة داخل كل قسم", default="1"),
    F("show_score_to_applicant", "Check", "إظهار العلامة للمتقدم بعد التسليم", default="0"),
    CB("exam_col"),
    F("pass_total", "Float", "الحد الأدنى للمجموع", default="50"),
    F("pass_aptitude", "Float", "الحد الأدنى للقدرات الذهنية", default="20"),
    F("track_min", "Float", "الحد الأدنى لقسم المسار المرغوب", default="10"),
    SB("privacy_section", "الخصوصية"),
    F("privacy_text", "Text Editor", "نص سياسة استخدام البيانات"),
]
write("Training Program Settings", settings,
      [{"role": "System Manager", "read": 1, "write": 1, "create": 1, "print": 1, "email": 1, "share": 1},
       {"role": "Training Manager", "read": 1, "write": 1, "create": 1, "print": 1, "email": 1, "share": 1}],
      issingle=1)

# "import" is a keyword in Python; DocPerm uses it as a key.
for name in ("training_exam_question",):
    p = os.path.join(BASE, name, name + ".json")
    s = open(p, encoding="utf-8").read().replace('"import_"', '"import"')
    open(p, "w", encoding="utf-8").write(s)
print("ok")
