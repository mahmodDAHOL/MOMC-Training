"""Fixed-layout fallback reader for the classic Syrian ID card.

Used alongside the label-based reader in syrian_id.py: on worn cards whose
thin printed labels are unreadable, the values themselves (bold, at known
row positions) are often still legible. syrian_id.read_card runs both and
keeps, field by field, the more trustworthy reading.
"""

from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass, field

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

    def as_dict(self) -> dict:
        return {"side": self.side, "fields": {k: asdict(v) for k, v in self.fields.items()}}


# Row centres as a fraction of card height, measured on real cards.
FRONT_ROWS = {
    "first_name": 0.34,
    "last_name": 0.44,
    "father_name": 0.57,
    "mother_name": 0.69,
    "birth": 0.80,
    "national_id": 0.92,
}
BACK_ROWS = {
    "governorate": 0.17,  # الأمانة
    "registry": 0.25,  # القيد
    "gender": 0.36,  # الجنس / لون الوجه / لون العينين
    "address": 0.45,
    "marks": 0.54,
    "issue_date": 0.64,  # تاريخ المنح
}
FRONT_VALUE_X = (0.38, 0.82)  # left of the label column, right of the photo
BACK_VALUE_X = (0.0, 0.86)
ROW_TOLERANCE = 0.055


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


def _tesseract_line(binary_ink: np.ndarray) -> str:
    import pytesseract

    img = cv2.copyMakeBorder(255 - binary_ink, 25, 25, 25, 25, cv2.BORDER_CONSTANT, value=255)
    return pytesseract.image_to_string(img, lang="ara", config="--psm 7").strip()


# --------------------------------------------------------------- images ---

def decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("not a readable image")
    return img


def _order_corners(pts: np.ndarray) -> np.ndarray:
    s, d = pts.sum(1), np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def flatten_card(img: np.ndarray) -> np.ndarray:
    """Perspective-correct the card onto the canvas (or just resize)."""
    h, w = img.shape[:2]
    scale = 1000 / max(h, w)
    small = cv2.resize(img, (int(w * scale), int(h * scale)))
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    edges = cv2.dilate(cv2.Canny(gray, 40, 120), np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = small.shape[0] * small.shape[1]
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(c) < 0.45 * area:
            break
        approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
        if len(approx) != 4:
            continue
        # A card that fills the whole frame is not worth warping.
        if cv2.contourArea(approx) > 0.92 * area:
            break
        src = _order_corners(approx.reshape(4, 2).astype(np.float32) / scale)
        width = np.linalg.norm(src[1] - src[0]) + np.linalg.norm(src[2] - src[3])
        height = np.linalg.norm(src[3] - src[0]) + np.linalg.norm(src[2] - src[1])
        if 1.35 <= width / max(height, 1) <= 1.85:  # card-shaped, not a panel on it
            dst = np.array([[0, 0], [CANVAS_W, 0], [CANVAS_W, CANVAS_H], [0, CANVAS_H]], np.float32)
            return cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst), (CANVAS_W, CANVAS_H))
    return cv2.resize(img, (CANVAS_W, CANVAS_H), interpolation=cv2.INTER_CUBIC)


def ink_masks(card: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(dark ink, red ink) binary masks, 255 = ink."""
    hsv = cv2.cvtColor(card, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    dark = cv2.medianBlur(((v < 110) * 255).astype(np.uint8), 3)
    red = (((h < 10) | (h > 165)) & (s > 70) & (v > 50)).astype(np.uint8) * 255
    red = cv2.medianBlur(cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)), 3)
    return dark, red


def value_rows(ink: np.ndarray, x_range: tuple[float, float], y_min: float) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of bold value text lines inside the value column."""
    h, w = ink.shape
    x0, x1 = int(x_range[0] * w), int(x_range[1] * w)
    region = np.zeros_like(ink)
    region[int(y_min * h):, x0:x1] = ink[int(y_min * h):, x0:x1]
    # Values are printed bold, labels thin: an opening keeps only bold strokes.
    bold = cv2.morphologyEx(region, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bold, 8)
    keep = np.zeros(n, bool)
    for i in range(1, n):
        _, _, bw, bh, area = stats[i]
        keep[i] = area > 80 and bh < 140 and bw < 0.25 * w
    bold = np.where(keep[labels], 255, 0).astype(np.uint8)
    lines = cv2.dilate(bold, cv2.getStructuringElement(cv2.MORPH_RECT, (60, 7)))
    contours, _ = cv2.findContours(lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = [cv2.boundingRect(c) for c in contours]
    return [b for b in boxes if b[2] > 60 and 30 < b[3] < 150]


def assign_rows(boxes, layout: dict[str, float], height: int) -> dict[str, tuple[int, int, int, int]]:
    """Merge boxes into rows and map each row to the closest layout slot."""
    rows: list[list[int]] = []  # [x0, y0, x1, y1]
    for x, y, w, h in sorted(boxes, key=lambda b: b[1] + b[3] / 2):
        cy = y + h / 2
        for r in rows:
            if abs((r[1] + r[3]) / 2 - cy) < 0.035 * height:
                r[0], r[1], r[2], r[3] = min(r[0], x), min(r[1], y), max(r[2], x + w), max(r[3], y + h)
                break
        else:
            rows.append([x, y, x + w, y + h])
    result: dict[str, tuple[int, int, int, int]] = {}
    for name, frac in layout.items():
        best, dist = None, ROW_TOLERANCE
        for r in rows:
            d = abs((r[1] + r[3]) / 2 / height - frac)
            if d < dist:
                best, dist = r, d
        if best is not None:
            result[name] = (best[0], best[1], best[2] - best[0], best[3] - best[1])
    return result


def _despeckle(binary: np.ndarray, min_area: int = 60) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    keep = stats[:, cv2.CC_STAT_AREA] >= min_area
    keep[0] = False
    return np.where(keep[labels], 255, 0).astype(np.uint8)


def _band(mask: np.ndarray, box, x_left: int, pad: int = 12) -> np.ndarray:
    """Crop one value row; starts a little left of the detected text but never
    before the value column, and drops background specks."""
    x, y, w, h = box
    left = max(x_left, x - 4 * pad)
    return _despeckle(mask[max(0, y - pad):y + h + pad, max(0, left):x + w + pad])


# ------------------------------------------------------------ extractors ---

def _name(dark, box, x_left) -> Field:
    raw = _tesseract_line(_band(dark, box, x_left))
    value = text.clean_name(text.after_label(raw))
    return Field(value, 0.7 if value else 0.0, raw)


def _place_and_number(dark, box, x_left) -> tuple[Field, list[str]]:
    band = _band(dark, box, x_left)
    groups, right = digits.number_run(band)
    raw = _tesseract_line(band[:, right + 8:] if right else band)
    place = text.clean_name(text.after_label(raw))
    return Field(place, 0.7 if place else 0.0, raw), groups


def _date_field(groups: list[str]) -> Field:
    parsed = text.parse_visual_date(groups)
    raw = "-".join(groups)
    if parsed and 1900 <= parsed.year <= 2100:
        return Field(parsed.isoformat(), 0.85, raw)
    return Field("", 0.0, raw)


def extract_front(card: np.ndarray) -> IDResult:
    dark, red = ink_masks(card)
    h, w = dark.shape
    x_left = int(FRONT_VALUE_X[0] * w)
    rows = assign_rows(value_rows(dark, FRONT_VALUE_X, 0.25), FRONT_ROWS, h)
    out = IDResult("front")
    for key in ("first_name", "last_name", "father_name", "mother_name"):
        out.fields[key] = _name(dark, rows[key], x_left) if key in rows else Field()
    if "birth" in rows:
        place, groups = _place_and_number(dark, rows["birth"], x_left)
        out.fields["birth_place"] = place
        out.fields["birth_date"] = _date_field(groups)
    else:
        out.fields["birth_place"], out.fields["birth_date"] = Field(), Field()
    # National number: red ink, bottom band, between photo and labels.
    band = red[int(0.84 * h):int(0.97 * h), int(0.30 * w):int(0.80 * w)]
    number = digits.read_number(band)
    if text.valid_national_id(number):
        out.fields["national_id"] = Field(number, 0.85, number)
    else:
        out.fields["national_id"] = Field("", 0.0, number)
    return out


def extract_back(card: np.ndarray) -> IDResult:
    dark, _ = ink_masks(card)
    h, w = dark.shape
    x_left = int(BACK_VALUE_X[0] * w)
    rows = assign_rows(value_rows(dark, BACK_VALUE_X, 0.05), BACK_ROWS, h)
    out = IDResult("back")
    out.fields["governorate"] = _name(dark, rows["governorate"], x_left) if "governorate" in rows else Field()
    if "registry" in rows:
        place, groups = _place_and_number(dark, rows["registry"], x_left)
        number = "".join(groups)
        out.fields["registry"] = Field(f"{place.value} {number}".strip(), place.confidence, place.raw)
    else:
        out.fields["registry"] = Field()
    if "gender" in rows:
        x, y, _, bh = rows["gender"]
        full_row = (x, y, int(BACK_VALUE_X[1] * w) - x, bh)  # gender sits far right
        raw = _tesseract_line(_band(dark, full_row, x_left))
        gender = text.detect_gender(raw)
        out.fields["gender"] = Field(gender or "", 0.75 if gender else 0.0, raw)
    else:
        out.fields["gender"] = Field()
    if "address" in rows:
        raw = _tesseract_line(_band(dark, rows["address"], x_left))
        address = text.after_label(raw)
        out.fields["address"] = Field(address, 0.5 if address else 0.0, raw)
    else:
        out.fields["address"] = Field()
    if "issue_date" in rows:
        groups, _ = digits.number_run(_band(dark, rows["issue_date"], x_left))
        out.fields["id_issue_date"] = _date_field(groups)
    else:
        out.fields["id_issue_date"] = Field()
    return out


def detect_side(card: np.ndarray) -> str:
    """Front has red national-number ink near the bottom; back does not."""
    _, red = ink_masks(card)
    h, w = red.shape
    band = red[int(0.84 * h):int(0.97 * h), int(0.30 * w):int(0.80 * w)]
    return "front" if cv2.countNonZero(band) > 0.004 * band.size else "back"
