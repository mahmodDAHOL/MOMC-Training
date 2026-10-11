"""Synthetic Syrian ID cards for measuring the OCR reader.

Every card gets random names, places, dates and numbers, a random font,
layout jitter (row positions, label/value spacing, scale), security-print
background, and photo-like damage: rotation, perspective, a table behind
the card, blur, noise, uneven light and JPEG compression. The ground truth
is returned with each image, so accuracy can be measured over hundreds of
cards instead of one sample.

Usage:  python tools/synth_cards.py OUT_DIR COUNT [FONT_DIR ...]
"""

from __future__ import annotations

import glob
import io
import json
import os
import random
import sys
from datetime import date, timedelta

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FIRST = ["سامر", "أحمد", "ريم", "هالة", "محمد", "يوسف", "لينا", "عمر", "رنا", "خالد", "مازن", "سلمى", "باسل", "نور", "طارق", "دانة", "وسيم", "جود"]
FATHER = ["أحمد", "محمود", "علي", "حسن", "إبراهيم", "سليم", "فايز", "نبيل", "عدنان", "محمد ديب", "عبد الله", "منير"]
LAST = ["الخطيب", "العلي", "الحسن", "شاهين", "النجار", "الحلبي", "السيد", "قباني", "المصري", "الشامي", "حداد", "يونس"]
MOTHER = ["هالة يوسف", "سعاد حمدان", "منى الأحمد", "فاطمة عيسى", "سميرة خليل", "نجوى سلوم", "ليلى حسون", "وفاء درويش"]
PLACE = ["دمشق", "حلب", "حمص", "حماة", "اللاذقية", "طرطوس", "درعا", "السويداء", "إدلب", "دير الزور", "الرقة", "القنيطرة"]
DIGITS = "٠١٢٣٤٥٦٧٨٩"


def ar_num(s: str) -> str:
    return "".join(DIGITS[int(c)] if c.isdigit() else c for c in s)


def default_fonts() -> list[str]:
    found = []
    for pattern in ("/usr/share/fonts/truetype/dejavu/DejaVuSans*.ttf", "/usr/share/fonts/truetype/freefont/FreeSerif*.ttf"):
        found += glob.glob(pattern)
    return [f for f in found if "Mono" not in f]


def _font_ok(path: str) -> bool:
    """True if the font's character map covers every letter and digit used."""
    from fontTools.ttLib import TTFont

    try:
        cmap = TTFont(path, lazy=True).getBestCmap() or {}
    except Exception:
        return False
    needed = set("".join(FIRST + FATHER + LAST + MOTHER + PLACE) + DIGITS + "الجمهوريةالعربيةالسوريةوزارةالداخليةالاسمالنسبةاسمالأبونسبةالأممحلتاريخالولادةالرقمالوطنيالأمانةالقيدالجنسذكرأنثىلونالوجهحنطيالعنوانالعلاماتالمميزةتامتاريخالمنح:-") - {" "}
    return all(ord(ch) in cmap for ch in needed)


def random_truth(rng: random.Random) -> dict:
    birth = date(1975, 1, 1) + timedelta(days=rng.randrange(0, 30 * 365))
    issue = date(2000, 1, 1) + timedelta(days=rng.randrange(0, 22 * 365))
    return {
        "first_name": rng.choice(FIRST),
        "last_name": rng.choice(LAST),
        "father_name": rng.choice(FATHER),
        "mother_name": rng.choice(MOTHER),
        "birth_place": rng.choice(PLACE),
        "birth_date": birth.isoformat(),
        "national_id": "".join(str(rng.randrange(10)) for _ in range(11)),
        "governorate": rng.choice(PLACE),
        "registry": f"{rng.choice(PLACE)} {rng.randrange(1, 400)}",
        "gender": rng.choice(["ذكر", "أنثى"]),
        "id_issue_date": issue.isoformat(),
    }


def _background(rng, w, h, tint):
    img = np.full((h, w, 3), tint, np.uint8)
    xs = np.arange(w)
    for _ in range(rng.randrange(18, 40)):
        color = tuple(int(c) for c in np.clip(np.array(tint) - rng.randrange(25, 60), 0, 255))
        amp, freq, phase = rng.uniform(5, 30), rng.uniform(0.004, 0.02), rng.uniform(0, 6)
        y0 = rng.randrange(0, h)
        ys = (y0 + amp * np.sin(xs * freq + phase)).astype(int)
        pts = np.stack([xs, ys], 1).reshape(-1, 1, 2)
        cv2.polylines(img, [pts], False, color, 1, cv2.LINE_AA)
    return Image.fromarray(img)


def _rtl(draw, right_x, y, text, font, fill):
    """Draw RTL text whose right edge sits at right_x; returns its left x."""
    width = draw.textlength(text, font=font, direction="rtl")
    draw.text((right_x - width, y), text, font=font, fill=fill, direction="rtl")
    return right_x - width


def render_card(truth: dict, side: str, rng: random.Random, fonts: list[str]) -> Image.Image:
    w, h = 1280, 808
    tint = (rng.randrange(225, 245), rng.randrange(230, 248), rng.randrange(215, 235))
    if side == "back":
        tint = (rng.randrange(235, 250), rng.randrange(215, 232), rng.randrange(220, 236))
    img = _background(rng, w, h, tint)
    draw = ImageDraw.Draw(img)
    font_path = rng.choice(fonts)
    size = rng.randrange(38, 48)
    label_font = ImageFont.truetype(font_path, size)
    value_font = ImageFont.truetype(rng.choice(fonts), size + rng.randrange(0, 6))
    blue = (rng.randrange(30, 70), rng.randrange(40, 80), rng.randrange(120, 170))
    ink = (rng.randrange(0, 30),) * 3
    red = (rng.randrange(170, 220), rng.randrange(20, 50), rng.randrange(20, 50))
    right = int(w * rng.uniform(0.95, 0.975))
    gap = rng.randrange(14, 40)

    if side == "front":
        _rtl(draw, right, 30, "الجمهورية العربية السورية", ImageFont.truetype(font_path, 50), blue)
        _rtl(draw, int(w * 0.8), 100, "وزارة الداخلية", ImageFont.truetype(font_path, 40), blue)
        draw.rectangle([40, 120, 330, 430], fill=(rng.randrange(60, 120),) * 3)  # photo
        rows = [
            ("الاسم:", truth["first_name"], ink),
            ("النسبة:", truth["last_name"], ink),
            ("اسم الأب:", truth["father_name"], ink),
            ("اسم و نسبة الأم :", truth["mother_name"], ink),
            ("محل و تاريخ الولادة:", f"{truth['birth_place']} {ar_num('-'.join(str(int(p)) for p in reversed(truth['birth_date'].split('-'))))}", ink),
            ("الرقم الوطني:", ar_num(truth["national_id"]), red),
        ]
        y, step = int(h * rng.uniform(0.29, 0.34)), int(h * rng.uniform(0.105, 0.125))
    else:
        rows = [
            ("الأمانة:", truth["governorate"], ink),
            ("القيد:", ar_num(truth["registry"]), ink),
            ("الجنس:", f"{truth['gender']}     لون الوجه: حنطي", ink),
            ("العنوان:", f"{truth['governorate']} {ar_num(str(rng.randrange(1000, 99999)))}", ink),
            ("العلامات المميزة:", "تام", ink),
            ("تاريخ المنح:", ar_num("-".join(str(int(p)) for p in reversed(truth["id_issue_date"].split("-")))), ink),
        ]
        y, step = int(h * rng.uniform(0.10, 0.15)), int(h * rng.uniform(0.085, 0.10))
        draw.rectangle([120, int(h * 0.72), int(w * 0.85), int(h * 0.95)], fill=(30, 30, 30))  # barcode band
    for label, value, color in rows:
        left = _rtl(draw, right, y + rng.randrange(-4, 5), label, label_font, blue)
        _rtl(draw, left - gap, y + rng.randrange(-4, 5), value, value_font, color)
        y += step + rng.randrange(-6, 7)
    return img


def photograph(card: Image.Image, rng: random.Random) -> bytes:
    """Place the card on a surface and apply camera-like damage."""
    card = np.array(card)
    h, w = card.shape[:2]
    canvas_w, canvas_h = int(w * rng.uniform(1.0, 1.35)), int(h * rng.uniform(1.0, 1.45))
    surface = np.full((canvas_h, canvas_w, 3), rng.choice([(40, 40, 45), (90, 60, 40), (150, 150, 150), (20, 25, 30)]), np.uint8)
    surface = cv2.add(surface, np.random.default_rng(rng.randrange(1 << 30)).integers(0, 25, surface.shape, dtype=np.uint8))
    angle = rng.uniform(-7, 7)
    # Shrink enough that the rotated card stays inside the frame.
    rad = np.deg2rad(abs(angle))
    fit = min(canvas_w / (w * np.cos(rad) + h * np.sin(rad)), canvas_h / (w * np.sin(rad) + h * np.cos(rad)))
    scale = min(fit, 1.0) * rng.uniform(0.9, 0.98)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, scale)
    m[0, 2] += (canvas_w - w) / 2
    m[1, 2] += (canvas_h - h) / 2
    warped = cv2.warpAffine(card, m, (canvas_w, canvas_h), borderValue=(0, 0, 0))
    mask = cv2.warpAffine(np.full((h, w), 255, np.uint8), m, (canvas_w, canvas_h))
    out = np.where(mask[..., None] > 0, warped, surface)
    # perspective
    d = rng.uniform(0, 0.025)
    src = np.float32([[0, 0], [canvas_w, 0], [canvas_w, canvas_h], [0, canvas_h]])
    jitter = np.float32([[rng.uniform(-d, d) * canvas_w, rng.uniform(-d, d) * canvas_h] for _ in range(4)])
    out = cv2.warpPerspective(out, cv2.getPerspectiveTransform(src, src + jitter), (canvas_w, canvas_h), borderMode=cv2.BORDER_REPLICATE)
    # uneven light, blur, noise
    gx = np.linspace(rng.uniform(0.75, 1.0), rng.uniform(0.95, 1.15), canvas_w)[None, :, None]
    out = np.clip(out * gx, 0, 255).astype(np.uint8)
    pil = Image.fromarray(out).filter(ImageFilter.GaussianBlur(rng.uniform(0, 1.3)))
    out = np.array(pil).astype(np.int16) + np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(0, 7), out.shape).astype(np.int16)
    pil = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    zoom = rng.uniform(0.7, 1.6)
    pil = pil.resize((int(canvas_w * zoom), int(canvas_h * zoom)))
    buf = io.BytesIO()
    pil.save(buf, "JPEG", quality=rng.randrange(55, 92))
    return buf.getvalue()


def make(seed: int, fonts: list[str] | None = None) -> tuple[dict, bytes, bytes]:
    rng = random.Random(seed)
    fonts = [f for f in (fonts or default_fonts()) if _font_ok(f)]
    truth = random_truth(rng)
    return truth, photograph(render_card(truth, "front", rng, fonts), rng), photograph(render_card(truth, "back", rng, fonts), rng)


if __name__ == "__main__":
    out, count = sys.argv[1], int(sys.argv[2])
    fonts = default_fonts() + [f for d in sys.argv[3:] for f in glob.glob(os.path.join(d, "*.ttf"))]
    os.makedirs(out, exist_ok=True)
    for i in range(count):
        truth, front, back = make(i, fonts)
        open(os.path.join(out, f"{i:04d}_front.jpg"), "wb").write(front)
        open(os.path.join(out, f"{i:04d}_back.jpg"), "wb").write(back)
        json.dump(truth, open(os.path.join(out, f"{i:04d}.json"), "w"), ensure_ascii=False)
    print(f"{count} cards in {out}")
