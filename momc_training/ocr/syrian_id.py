"""Field extraction from Syrian national ID cards — layout independent.

Fixed pixel positions break as soon as a card is photographed at an angle,
printed with a different font, or issued in a slightly different layout.
This reader instead *finds the printed labels* (الاسم، النسبة، الرقم الوطني …)
on whatever it sees and reads the value printed next to each label:

1. Card: find the card in the photo and flatten it (perspective), turn it
   upright (portrait shots, upside-down shots) and straighten small tilts.
2. Ink: separate printed text from the security background with a
   black-hat filter, which adapts to uneven light and card colour.
3. Lines: group ink into text lines, whatever their position or spacing.
4. Labels: OCR each line (Tesseract, Arabic), fuzzy-match its right-most
   words against known labels, and take everything to the left as the value.
5. Values: letters from Tesseract; Arabic-Indic digits from digits.py.
6. Checks: national number must have 11 digits, dates must be real dates.
   A field whose label was not found falls back to pattern search (any
   11-digit number, any date) or to the usual row position, with lower
   confidence.

The output is a suggestion: each field carries a confidence and the
applicant confirms or corrects it before saving.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher

import cv2
import numpy as np

from . import digits, text

CANVAS_W = 2560
CANVAS_H = int(CANVAS_W / 1.585)  # ID-1 card aspect ratio (85.6 x 54 mm)


class OCRUnavailable(RuntimeError):
    """Tesseract or its Arabic model is not installed on the server."""


@dataclass
class Field:
    value: str = ""
    confidence: float = 0.0  # 0..1; 0 means not found
    raw: str = ""


@dataclass
class IDResult:
    side: str
    fields: dict[str, Field] = field(default_factory=dict)
    labels_found: int = 0

    def as_dict(self) -> dict:
        return {"side": self.side, "fields": {k: asdict(v) for k, v in self.fields.items()}}


# Label spellings seen on Syrian cards (normalised by _norm before matching).
LABELS = {
    "front": {
        "first_name": ["الاسم"],
        "last_name": ["النسبة", "الكنية"],
        "father_name": ["اسم الاب"],
        "mother_name": ["اسم ونسبة الام", "اسم الام"],
        "birth": ["محل وتاريخ الولادة", "مكان وتاريخ الولادة", "تاريخ الولادة"],
        "national_id": ["الرقم الوطني"],
    },
    "back": {
        "governorate": ["الامانة"],
        "registry": ["القيد", "رقم القيد"],
        "gender": ["الجنس"],
        "address": ["العنوان"],
        "marks": ["العلامات المميزة"],
        "issue_date": ["تاريخ المنح"],
    },
}
OUTPUT_FIELDS = {
    "front": ["first_name", "last_name", "father_name", "mother_name", "birth_place", "birth_date", "national_id"],
    "back": ["governorate", "registry", "gender", "address", "id_issue_date"],
}
# Last-resort row positions (fraction of card height) when a label is unreadable.
FALLBACK_ROWS = {
    "front": {"first_name": 0.34, "last_name": 0.44, "father_name": 0.57, "mother_name": 0.69, "birth": 0.80},
    "back": {"governorate": 0.17, "registry": 0.25, "gender": 0.36, "address": 0.45, "issue_date": 0.64},
}
LABEL_MIN_RATIO = 0.72
PLACE_FIELDS = ("governorate", "birth_place", "registry")


# --------------------------------------------------------------- engine ---

def ensure_engine() -> None:
    try:
        import pytesseract
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise OCRUnavailable("pytesseract is not installed") from exc
    if not shutil.which(pytesseract.pytesseract.tesseract_cmd or "tesseract"):
        raise OCRUnavailable("tesseract binary not found")
    if "ara" not in pytesseract.get_languages(config=""):
        raise OCRUnavailable("Arabic model (ara.traineddata) not installed")


@dataclass
class Word:
    text: str
    x: int
    w: int


def _ocr_words(binary_ink: np.ndarray) -> list[Word]:
    """Words of one text line, right to left (Arabic reading order)."""
    import pytesseract

    pad = 25
    img = cv2.copyMakeBorder(255 - binary_ink, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
    data = pytesseract.image_to_data(img, lang="ara", config="--psm 7", output_type=pytesseract.Output.DICT)
    words = [
        Word(t.strip(), x - pad, w)
        for t, x, w, conf in zip(data["text"], data["left"], data["width"], data["conf"], strict=True)
        if t.strip() and float(conf) > -1
    ]
    return sorted(words, key=lambda wd: -(wd.x + wd.w))


# --------------------------------------------------------------- images ---

def decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not a readable image")
    return img


def _order_corners(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def _card_quad(img: np.ndarray) -> np.ndarray | None:
    """Corners of the card in the photo, or None if it fills the frame."""
    h, w = img.shape[:2]
    scale = 900 / max(h, w)
    small = cv2.resize(img, (int(w * scale), int(h * scale)))
    area = small.shape[0] * small.shape[1]
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    candidates = []
    # Edges, plus a brightness split: cards are usually lighter than the table.
    edges = cv2.dilate(cv2.Canny(gray, 30, 110), np.ones((5, 5), np.uint8))
    _, bright = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    for mask in (edges, bright):
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
            hull = cv2.convexHull(c)
            a = cv2.contourArea(hull)
            if not 0.25 * area < a < 0.97 * area:
                continue
            approx = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
            if len(approx) != 4:
                rect = cv2.minAreaRect(hull)
                approx = cv2.boxPoints(rect).reshape(-1, 1, 2)
            quad = _order_corners(approx.reshape(4, 2).astype(np.float32))
            width = np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])
            height = np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])
            ratio = max(width, height) / max(min(width, height), 1)
            if 1.3 <= ratio <= 1.9:
                candidates.append((a, quad))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[0])[1] / scale


def flatten_card(img: np.ndarray) -> np.ndarray:
    """Perspective-correct the card onto a landscape canvas."""
    quad = _card_quad(img)
    if quad is not None:
        width = np.linalg.norm(quad[1] - quad[0])
        height = np.linalg.norm(quad[3] - quad[0])
        if height > width:  # card photographed in portrait
            quad = np.roll(quad, -1, axis=0)
        dst = np.array([[0, 0], [CANVAS_W, 0], [CANVAS_W, CANVAS_H], [0, CANVAS_H]], np.float32)
        return cv2.warpPerspective(img, cv2.getPerspectiveTransform(quad, dst), (CANVAS_W, CANVAS_H))
    h, w = img.shape[:2]
    if h > w:
        img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    return cv2.resize(img, (CANVAS_W, CANVAS_H), interpolation=cv2.INTER_CUBIC)


def ink_mask(card: np.ndarray) -> np.ndarray:
    """Printed text (dark, red or blue) as 255 on 0, background removed.

    A black-hat filter keeps marks darker than their surroundings and smaller
    than the kernel — characters — and ignores slow changes in light and the
    card's colour. The pale security lines fall under the Otsu threshold.
    """
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
    k = max(15, int(card.shape[0] * 0.035)) | 1
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    blackhat = cv2.GaussianBlur(blackhat, (3, 3), 0)
    otsu, _ = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, mask = cv2.threshold(blackhat, max(otsu, 28), 255, cv2.THRESH_BINARY)
    return _despeckle(cv2.medianBlur(mask, 3), max(20, card.shape[0] // 60))


def _despeckle(binary: np.ndarray, min_area: int = 60) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def _drop_big_blobs(mask: np.ndarray) -> np.ndarray:
    """Remove photo, emblem, barcode and long cracks — anything not text-sized."""
    h, w = mask.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        too_tall = bh > 0.11 * h
        too_wide_thin = bw > 0.25 * w and area < 0.08 * bw * bh
        keep[i] = not too_tall and not too_wide_thin
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def deskew(card: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Straighten small tilts (±8°) by maximising row-projection sharpness."""
    small = cv2.resize(mask, (640, int(640 * mask.shape[0] / mask.shape[1])))
    best, best_angle = -1.0, 0.0
    center = (small.shape[1] / 2, small.shape[0] / 2)
    for angle in np.arange(-8, 8.01, 0.5):
        rot = cv2.warpAffine(small, cv2.getRotationMatrix2D(center, angle, 1.0), small.shape[::-1])
        score = float(np.var(rot.sum(1)))
        if score > best:
            best, best_angle = score, angle
    if abs(best_angle) < 0.25:
        return card, mask
    h, w = mask.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), best_angle, 1.0)
    card = cv2.warpAffine(card, m, (w, h), borderMode=cv2.BORDER_REPLICATE)
    mask = cv2.warpAffine(mask, m, (w, h))
    _, mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)
    return card, mask


def text_lines(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Boxes of text lines (x, y, w, h), top to bottom."""
    h, w = mask.shape
    clean = _drop_big_blobs(mask)
    joined = cv2.dilate(clean, cv2.getStructuringElement(cv2.MORPH_RECT, (max(25, w // 45), 5)))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) for c in contours]
    boxes = [b for b in boxes if b[2] > w * 0.04 and h * 0.018 < b[3] < h * 0.13]
    return sorted(boxes, key=lambda b: (b[1] + b[3] / 2, -b[0]))


# -------------------------------------------------------------- labels ---

_ALEF = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ؤ": "و", "ئ": "ي", "ة": "ه", "ى": "ي"})


def _norm(value: str) -> str:
    value = text.clean(value).translate(_ALEF)
    return re.sub(r"[^ء-ي]", "", value)


@dataclass
class Line:
    box: tuple[int, int, int, int]
    words: list[Word]
    key: str = ""
    ratio: float = 0.0
    label_left: int = 0  # card x where the label starts; the value lies to its left


def match_label(words: list[Word], labels: dict[str, list[str]]) -> tuple[str, float, int]:
    """Best (field, ratio, label_left_x) for a line's right-most words."""
    best = ("", 0.0, 0)
    for n in range(1, min(5, len(words)) + 1):
        head = words[:n]
        candidate = _norm("".join(w.text.split(":")[0] if i == n - 1 else w.text for i, w in enumerate(head)))
        if not candidate:
            continue
        for key, spellings in labels.items():
            for spelling in spellings:
                target = _norm(spelling)
                ratio = SequenceMatcher(None, candidate, target).ratio()
                # Long labels may be cut short by the colon or a missed word.
                if len(candidate) < len(target):
                    ratio = max(ratio, SequenceMatcher(None, candidate, target[: len(candidate)]).ratio() * 0.9)
                if ratio > best[1]:
                    best = (key, ratio, min(w.x for w in head))
    return best


def find_labels(lines: list[Line], labels: dict[str, list[str]]) -> dict[str, Line]:
    """Assign each label to the line that matches it best (one line per label)."""
    scored = []
    for line in lines:
        key, ratio, left = match_label(line.words, labels)
        if key and ratio >= LABEL_MIN_RATIO:
            scored.append((ratio, key, left, line))
    found: dict[str, Line] = {}
    used: set[int] = set()
    for ratio, key, left, line in sorted(scored, key=lambda s: -s[0]):
        if key in found or id(line) in used:
            continue
        # A colon read as its own word belongs to the label, not the value.
        for w in line.words:
            if w.x + w.w <= left + 4 and not re.sub(r"[:.؛،\s]", "", w.text):
                left = min(left, w.x)
            elif w.x + w.w <= left + 4:
                break
        line.key, line.ratio, line.label_left = key, ratio, left
        found[key] = line
        used.add(id(line))
    return found


# ------------------------------------------------------------- reading ---

def _value_crop(mask: np.ndarray, line: Line, label_left: int | None) -> np.ndarray:
    """Ink of the row left of its label (whole row if no label)."""
    x, y, w, h = line.box
    pad = max(6, h // 5)
    right = x + w + pad if label_left is None else max(x + 1, label_left - max(8, h // 4))
    crop = mask[max(0, y - pad):y + h + pad, max(0, x - pad):right]
    return _despeckle(crop, max(12, h // 6))


def _value_text(line: Line, label_left: int | None) -> tuple[str, str]:
    raw = " ".join(w.text for w in reversed(line.words))
    if label_left is None:
        return raw, text.after_label(raw)
    value_words = [w for w in line.words if w.x + w.w <= label_left + 4]
    value = " ".join(w.text for w in value_words)  # right-to-left = logical order
    return raw, text.after_label(value) if ":" in value else value


def _tesseract_digits(crop: np.ndarray) -> str:
    """Second opinion on a number, from Tesseract restricted to digits."""
    import pytesseract

    img = cv2.copyMakeBorder(255 - crop, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    out = pytesseract.image_to_string(
        img, lang="ara", config="--psm 7 -c tessedit_char_whitelist=٠١٢٣٤٥٦٧٨٩0123456789-"
    )
    return text.to_latin_digits(out)


def _agree(primary: str, crop: np.ndarray) -> bool:
    second = re.sub(r"\D", "", _tesseract_digits(crop))
    return bool(primary) and primary in second


def _place_and_number(mask: np.ndarray, line: Line, label_left: int | None):
    """Split a 'place number' value (محل الولادة والتاريخ، القيد).

    The number sits at the left end of the value; the place is the words
    between the number and the label. Returns (place, digit groups, raw, crop).
    """
    crop = _value_crop(mask, line, label_left)
    groups, run_right = digits.number_run(crop)
    crop_x0 = max(0, line.box[0] - max(6, line.box[3] // 5))
    raw, _ = _value_text(line, label_left)
    limit = label_left if label_left is not None else line.box[0] + line.box[2] + 1
    in_value = [w for w in line.words if w.x + w.w <= limit + 4]
    if not in_value and label_left is not None:  # value missed in the row pass
        in_value = [Word(w.text, w.x + crop_x0, w.w) for w in _ocr_words(crop)]
    words = [w for w in in_value if w.x >= crop_x0 + run_right - 4] or in_value
    letters = re.sub(r"[^\u0621-\u064a\s]", " ", " ".join(w.text for w in words))
    return text.correct_place(letters), groups, raw, crop


def _date(groups: list[str], conf: float) -> Field:
    parsed = text.parse_visual_date(groups)
    raw = "-".join(groups)
    if parsed and 1900 <= parsed.year <= 2100:
        return Field(parsed.isoformat(), conf, raw)
    return Field("", 0.0, raw)


def ocr_lines(mask: np.ndarray) -> list[Line]:
    """OCR every text segment, then join segments that sit on the same row.

    A label and its value are often far apart on the card, so they come out
    as separate segments; joining by row puts them back together. Word x
    positions are kept in card coordinates.
    """
    segments = []
    for box in text_lines(mask):
        x, y, w, h = box
        pad = max(6, h // 5)
        x0 = max(0, x - pad)
        crop = mask[max(0, y - pad):y + h + pad, x0:x + w + pad]
        words = [Word(wd.text, wd.x + x0, wd.w) for wd in _ocr_words(crop)]
        if words:
            segments.append(Line(box, words))
    rows: list[Line] = []
    for seg in sorted(segments, key=lambda sg: -(sg.box[0] + sg.box[2])):  # right-most first
        x, y, w, h = seg.box
        cy = y + h / 2
        for row in rows:
            rx, ry, rw, rh = row.box
            if abs((ry + rh / 2) - cy) < 0.6 * max(h, rh) and x + w <= rx + rw:
                nx, ny = min(rx, x), min(ry, y)
                row.box = (nx, ny, max(rx + rw, x + w) - nx, max(ry + rh, y + h) - ny)
                row.words = sorted(row.words + seg.words, key=lambda wd: -(wd.x + wd.w))
                break
        else:
            rows.append(Line(seg.box, list(seg.words)))
    return sorted(rows, key=lambda r: r.box[1] + r.box[3] / 2)


def _read_side(card: np.ndarray, mask: np.ndarray, ocr: list[Line], side: str) -> IDResult:
    lines = [Line(ln.box, ln.words) for ln in ocr]  # fresh label state per side
    found = find_labels(lines, LABELS[side])
    result = IDResult(side, labels_found=len(found))
    height = mask.shape[0]

    def line_for(key: str) -> tuple[Line | None, float]:
        if key in found:
            return found[key], 0.85
        # Fallback: the unlabelled line nearest the usual row position.
        frac = FALLBACK_ROWS[side].get(key)
        free = [ln for ln in lines if not ln.key]
        if frac is None or not free:
            return None, 0.0
        near = min(free, key=lambda ln: abs((ln.box[1] + ln.box[3] / 2) / height - frac))
        if abs((near.box[1] + near.box[3] / 2) / height - frac) > 0.06:
            return None, 0.0
        return near, 0.45

    def label_left(line: Line) -> int | None:
        return line.label_left if line.key else None

    def name(key: str) -> Field:
        line, conf = line_for(key)
        if not line:
            return Field()
        raw, value = _value_text(line, label_left(line) if line.key else None)
        value = text.clean_name(value)
        if not value and line.key:
            words = _ocr_words(_value_crop(mask, line, label_left(line)))
            value = text.clean_name(" ".join(w.text for w in words))
        # Letters have no independent check, so even a labelled name is a
        # "please confirm" suggestion.
        return Field(value, min(conf, 0.75) if value else 0.0, raw)

    if side == "front":
        for key in ("first_name", "last_name", "father_name", "mother_name"):
            result.fields[key] = name(key)
        line, conf = line_for("birth")
        if line:
            place, groups, raw, crop = _place_and_number(mask, line, label_left(line))
            result.fields["birth_place"] = Field(place, conf if place else 0.0, raw)
            date_field = _date(groups, conf)
            if date_field.value and not _agree("".join(groups), crop):
                date_field.confidence = min(date_field.confidence, 0.6)
            result.fields["birth_date"] = date_field
        result.fields["national_id"] = _national_id(card, mask, found.get("national_id"), lines, label_left)
    else:
        gov = name("governorate")
        gov.value = text.correct_place(gov.value) if gov.value else ""
        result.fields["governorate"] = gov
        line, conf = line_for("registry")
        if line:
            place, groups, raw, _ = _place_and_number(mask, line, label_left(line))
            number = "".join(groups)
            # The number has no second reader to agree with: always ask to confirm.
            conf = min(conf, 0.7) if place and number else min(conf, 0.5)
            result.fields["registry"] = Field(f"{place} {number}".strip(), conf if place else 0.0, raw)
        line, conf = line_for("gender")
        if line:
            raw = " ".join(w.text for w in reversed(line.words))
            after_label = [w for w in line.words if line.key and w.x + w.w <= line.label_left + 4]
            gender = (text.gender_from_word(after_label[0].text) if after_label else None) or text.detect_gender(raw)
            result.fields["gender"] = Field(gender or "", conf if gender else 0.0, raw)
        line, conf = line_for("address")
        if line:
            raw, value = _value_text(line, label_left(line))
            result.fields["address"] = Field(text.clean(value), min(conf, 0.5) if value else 0.0, raw)
        line, conf = line_for("issue_date")
        if line:
            crop = _value_crop(mask, line, label_left(line))
            groups, _ = digits.number_run(crop)
            issue = _date(groups, conf)
            if issue.value and not _agree("".join(groups), crop):
                issue.confidence = min(issue.confidence, 0.6)
            result.fields["id_issue_date"] = issue
    for key in OUTPUT_FIELDS[side]:
        result.fields.setdefault(key, Field())
    return result


def _national_id(card, mask, labelled: Line | None, lines: list[Line], label_left) -> Field:
    """11 digits: next to its label if found, else any line holding exactly 11 digits."""
    candidates: list[tuple[float, Line]] = []
    if labelled:
        candidates.append((0.9, labelled))
    candidates += [(0.6, ln) for ln in sorted(lines, key=lambda ln: -ln.box[1]) if ln is not labelled]
    for conf, line in candidates:
        crop = _value_crop(mask, line, label_left(line) if line.key else None)
        number = digits.read_number(crop)
        if text.valid_national_id(number):
            # Two independent readers agreeing earns full confidence;
            # otherwise the applicant is asked to check it.
            return Field(number, conf if _agree(number, crop) else min(conf, 0.6), number)
        # Labels and other text can add stray "digits"; accept a clean 11-run inside.
        run = re.search(r"\d{11}", number)
        if run and len(number) <= 13:
            return Field(run.group(0), conf - 0.2, number)
    return Field()


def _upright_candidates(card: np.ndarray) -> list[np.ndarray]:
    return [card, cv2.rotate(card, cv2.ROTATE_180)]


def _layout_reading(image: np.ndarray, side: str) -> dict:
    """Fixed-row reading (layout.py), cross-checked like the dynamic one."""
    from . import layout

    card = layout.flatten_card(image)
    result = (layout.extract_front if side == "front" else layout.extract_back)(card).as_dict()["fields"]
    dark, red = layout.ink_masks(card)
    h, w = dark.shape
    nid = result.get("national_id")
    if nid and nid["value"]:
        band = red[int(0.84 * h):int(0.97 * h), int(0.30 * w):int(0.80 * w)]
        if not _agree(nid["value"], band):
            nid["confidence"] = min(nid["confidence"], 0.6)
    for key in ("birth_date", "id_issue_date"):
        if result.get(key, {}).get("value"):
            result[key]["confidence"] = min(result[key]["confidence"], 0.7)
    for key in ("governorate", "birth_place"):
        if result.get(key, {}).get("value"):
            result[key]["value"] = text.correct_place(result[key]["value"])
    reg = result.get("registry")
    if reg and reg["value"]:
        number = " ".join(re.findall(r"\d+", text.to_latin_digits(reg["value"])))
        place = text.correct_place(re.sub(r"[^\u0621-\u064a\s]", " ", reg["value"]))
        reg["value"] = f"{place} {number}".strip()
    return result


def _valid(key: str, value: str) -> bool:
    if not value:
        return False
    if key == "national_id":
        return text.valid_national_id(value)
    if key in ("birth_date", "id_issue_date"):
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))
    return len(text.clean(value)) >= 2


def merge(dynamic: dict, fixed: dict) -> dict:
    """Per field, keep the valid reading with the higher confidence.

    When both readers produced different valid values, the field is marked
    for checking (confidence capped) because one of them is wrong.
    """
    out = {}
    for key in set(dynamic) | set(fixed):
        a, b = dynamic.get(key) or {}, fixed.get(key) or {}
        options = [o for o in (a, b) if _valid(key, o.get("value", ""))]
        if not options:
            out[key] = {"value": "", "confidence": 0.0, "raw": a.get("raw") or b.get("raw", "")}
            continue
        def score(o, key=key):
            # A place that snapped to a known Syrian place name is more credible.
            place = o["value"].split(" ")[0] if key == "registry" else o["value"]
            bonus = 0.2 if key in PLACE_FIELDS and text.is_known_place(place) else 0.0
            return o.get("confidence", 0) + bonus

        best = dict(max(options, key=score))
        if len(options) == 2 and text.clean(a["value"]) != text.clean(b["value"]):
            best["confidence"] = min(best.get("confidence", 0), 0.6)
        elif len(options) == 2:
            best["confidence"] = max(a.get("confidence", 0), b.get("confidence", 0))
        out[key] = best
    return out


def read_card(data: bytes, side: str | None = None) -> dict:
    """Entry point: image bytes -> {'side', 'fields': {name: {value, confidence, raw}}}.

    `side` ("front"/"back") is a hint from the upload slot; if the labels say
    the other side was uploaded, the labels win.
    """
    ensure_engine()
    image = decode(data)
    card = flatten_card(image)
    best: IDResult | None = None
    for turn, candidate in enumerate(_upright_candidates(card)):
        mask = ink_mask(candidate)
        candidate, mask = deskew(candidate, mask)
        lines = ocr_lines(mask)
        results = [_read_side(candidate, mask, lines, s) for s in ([side] if side else []) + [s for s in ("front", "back") if s != side]]
        top = max(results, key=lambda r: (r.labels_found, r.side == side))
        # Turning the card over must clearly beat the upright reading.
        if best is None or (top.labels_found >= 2 and top.labels_found > best.labels_found + (1 if turn else 0)):
            best = top
        if best.labels_found >= 3:
            break
    reading = best.as_dict()
    if best.labels_found < 2:
        from . import layout

        reading["side"] = side or layout.detect_side(layout.flatten_card(image))
    dynamic = reading["fields"] if reading["side"] == best.side and best.labels_found else {}
    reading["fields"] = merge(dynamic, _layout_reading(image, reading["side"]))
    for key in OUTPUT_FIELDS[reading["side"]]:
        reading["fields"].setdefault(key, {"value": "", "confidence": 0.0, "raw": ""})
    return reading
