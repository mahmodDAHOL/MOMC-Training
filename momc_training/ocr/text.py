"""Pure text helpers for Arabic OCR output (no Frappe, no OpenCV)."""

from __future__ import annotations

import re
from datetime import date

ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
PERSIAN = "۰۱۲۳۴۵۶۷۸۹"
_DIGIT_MAP = {ord(c): str(i) for i, c in enumerate(ARABIC_INDIC)}
_DIGIT_MAP.update({ord(c): str(i) for i, c in enumerate(PERSIAN)})

_TATWEEL = "ـ"
_DIACRITICS = re.compile("[ً-ْٰ]")
_BIDI_MARKS = re.compile("[‎‏‪-‮⁦-⁩]")
_NON_ARABIC_NAME = re.compile(r"[^ء-ي\s]")


def to_latin_digits(value: str) -> str:
    return (value or "").translate(_DIGIT_MAP)


def clean(value: str) -> str:
    """Strip bidi marks, tatweel, diacritics and collapse whitespace."""
    value = _BIDI_MARKS.sub("", value or "")
    value = value.replace(_TATWEEL, "")
    value = _DIACRITICS.sub("", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_name(value: str) -> str:
    """Keep Arabic letters and spaces only — for name fields."""
    value = _NON_ARABIC_NAME.sub(" ", clean(value))
    words = [w for w in value.split() if len(w) > 1 or w in ("و",)]
    return " ".join(words)


def after_label(value: str) -> str:
    """'اسم الأم : خديجة' -> 'خديجة' (label leaked into a value crop)."""
    value = clean(value)
    for sep in (":", "؛", "؟"):
        if sep in value:
            value = value.rsplit(sep, 1)[1]
    return value.strip()


def valid_national_id(value: str) -> bool:
    """Syrian national number: exactly 11 digits."""
    return bool(re.fullmatch(r"\d{11}", to_latin_digits(value or "")))


def parse_visual_date(groups: list[str]) -> date | None:
    """Parse digit groups in *visual* left-to-right order.

    Syrian cards print d-m-yyyy in an RTL line, so read left to right the
    groups come out as [yyyy, m, d]. Accepts either order defensively, and
    ignores stray digits a reader may glue to the ends (dots of the next
    word read as zeros: ['1998', '5', '150'] -> 1998-05-15).
    """
    groups = [to_latin_digits(g) for g in groups if g and g.strip("-")]
    if len(groups) < 3 or not all(g.isdigit() for g in groups[:3]):
        return None
    candidates = []
    a, b, c = groups[:3]
    if len(a) >= 4:
        candidates += [(a[-4:], b, d) for d in (c[:2], c[:1])]
    if len(c) >= 4:
        candidates += [(c[:4], b, d) for d in (a[-2:], a[-1:])]
    for y, m, d in candidates:
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            continue
    return None


def split_place_and_date(line: str) -> tuple[str, list[str]]:
    """'دمشق 6-8-1999' -> ('دمشق', ['6','8','1999']) in logical order."""
    line = to_latin_digits(clean(line))
    m = re.search(r"(\d{1,4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,4})", line)
    if not m:
        return clean_name(line), []
    place = clean_name(line[: m.start()] + " " + line[m.end():])
    return place, list(m.groups())


GENDER_MALE = "ذكر"
GENDER_FEMALE = "أنثى"


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def detect_gender(text: str) -> str | None:
    """Find ذكر / أنثى in a noisy OCR line (Tesseract often reads ذكر as
    كثر or دكر)."""
    words = clean(text).replace("أ", "ا").replace("ي", "ى").split()
    for w in words:
        w = w.strip(":-.،")
        # ذ is often lost or split: accept one wrong letter, or a 3-letter
        # word ending in ر that keeps the ك (كثر، دكر، ذكر).
        if len(w) == 3 and (_edit_distance(w, "ذكر") <= 1 or (w[2] == "ر" and "ك" in w[:2])):
            return GENDER_MALE
        if len(w) == 4 and _edit_distance(w, "انثى") <= 1:
            return GENDER_FEMALE
    return None


# Syrian governorates and larger towns, for correcting one-letter OCR slips
# in place fields (دزعا -> درعا). Only near matches are corrected.
PLACES = (
    "دمشق ريف دمشق حلب حمص حماة اللاذقية طرطوس إدلب درعا السويداء القنيطرة دير الزور الرقة الحسكة "
    "القامشلي منبج الباب عفرين جبلة بانياس صافيتا مصياف السلمية تدمر النبك يبرود الزبداني دوما "
    "جرمانا التل قطنا داريا معضمية الشام الكسوة صيدنايا معرة النعمان أريحا جسر الشغور سراقب "
    "خان شيخون محمبل البوكمال الميادين الطبقة تل أبيض رأس العين المالكية عامودا نوى إزرع "
    "الصنمين بصرى الشام شهبا صلخد القريتين القصير الرستن تلكلخ محردة السقيلبية الدريكيش "
    "الشيخ بدر القرداحة الحفة الميدان المزة"
)
_PLACE_LIST = None


def _places() -> list[str]:
    global _PLACE_LIST
    if _PLACE_LIST is None:
        multi = ["ريف دمشق", "دير الزور", "معرة النعمان", "جسر الشغور", "خان شيخون", "تل أبيض", "رأس العين",
                 "بصرى الشام", "معضمية الشام", "الشيخ بدر"]
        _PLACE_LIST = multi + PLACES.split()
    return _PLACE_LIST


def correct_place(value: str, min_ratio: float = 0.75) -> str:
    """Snap a place name to the closest known one if it is a near miss."""
    from difflib import SequenceMatcher

    value = clean_name(value)
    if not value:
        return value
    key = value.replace("أ", "ا").replace("إ", "ا").replace("ة", "ه")
    best, score = value, 0.0
    for place in _places():
        p = place.replace("أ", "ا").replace("إ", "ا").replace("ة", "ه")
        r = SequenceMatcher(None, key, p).ratio()
        if r > score:
            best, score = place, r
    return best if score >= min_ratio else value


def gender_from_word(word: str) -> str | None:
    """Gender from the word printed right after the الجنس label, even if
    Tesseract kept only part of it (ذ / ذو / كر)."""
    w = clean(word).strip(":-.،").replace("أ", "ا")
    if not w:
        return None
    if w.startswith(("ذ", "د")) and len(w) <= 4 or w in ("كر", "كثر"):
        return GENDER_MALE
    if w.startswith("ا") and ("ن" in w or "ث" in w):
        return GENDER_FEMALE
    return None


def is_known_place(value: str) -> bool:
    return clean_name(value) in _places()
