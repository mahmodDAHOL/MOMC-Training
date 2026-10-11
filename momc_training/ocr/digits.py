"""Arabic-Indic digit reader.

Tesseract's Arabic model reads printed Arabic-Indic digits on Syrian ID
cards poorly, so numeric fields are read with a small template classifier:
each connected component is normalised to a 32x32 shape vector and
compared (cosine similarity, with a counter/hole check) with templates rendered from several fonts at build time
(digit_templates.npz, see tools/build_digit_templates.py). Zero (a small dot/diamond) and hyphen are decided by
geometry relative to the median digit height.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

_SIZE = 32
_MIN_SCORE = 0.72
_TEMPLATES = os.path.join(os.path.dirname(__file__), "digit_templates.npz")


@dataclass
class Glyph:
    x: int
    y: int
    w: int
    h: int
    char: str  # "0".."9", "-", or "?"
    score: float


@lru_cache(maxsize=1)
def _templates() -> tuple[np.ndarray, np.ndarray]:
    data = np.load(_TEMPLATES)
    return data["X"].astype(np.float32), data["Y"].astype(int)


def descriptor(component: np.ndarray) -> np.ndarray:
    """Shape vector for a binary glyph (255 = ink): centred square, 32x32.

    Templates are rendered at several stroke weights, so bold card print and
    thinner font outlines both find a close neighbour.
    """
    ys, xs = np.nonzero(component)
    if len(ys) == 0:
        return np.zeros(_SIZE * _SIZE, np.float32)
    component = component[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = component.shape
    side = max(h, w)
    pad = np.zeros((side, side), np.uint8)
    pad[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = component
    vec = cv2.resize(pad, (_SIZE, _SIZE), interpolation=cv2.INTER_AREA).astype(np.float32).reshape(-1)
    return vec / (np.linalg.norm(vec) + 1e-6)


def has_hole(component: np.ndarray) -> bool:
    """True if the glyph encloses a counter (as in ٥ and ٩)."""
    contours, hierarchy = cv2.findContours(component, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return False
    min_area = 0.01 * component.shape[0] * component.shape[1]
    return any(h[3] >= 0 and cv2.contourArea(c) >= min_area for c, h in zip(contours, hierarchy[0], strict=True))


_HOLED = {5, 9}
_HOLE_PENALTY = 0.06


def classify(component: np.ndarray) -> tuple[str, float]:
    """Return (digit, cosine score) for a binary component (255 = ink)."""
    vec = descriptor(component)
    x, y = _templates()
    scores = x @ vec
    holed = has_hole(component)
    scores = scores - _HOLE_PENALTY * np.array([(d in _HOLED) != holed for d in y], dtype=np.float32)
    best = int(np.argmax(scores))
    return str(y[best]), float(scores[best])


def components(binary: np.ndarray, min_area: int = 25) -> list[tuple[int, int, int, int]]:
    """Bounding boxes of connected components, left to right."""
    n, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    boxes = [tuple(int(v) for v in stats[i][:4]) for i in range(1, n) if stats[i][4] >= min_area]
    return sorted(boxes, key=lambda b: b[0])


def _merge_split(boxes: list[tuple[int, int, int, int]], ref: float) -> list[tuple[int, int, int, int]]:
    """Join strokes of one glyph that print broke apart (e.g. the arms of ٧)."""
    merged: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if merged:
            px, py, pw, ph = merged[-1]
            x, y, w, h = box
            gap = x - (px + pw)
            x0, y0 = min(px, x), min(py, y)
            x1, y1 = max(px + pw, x + w), max(py + ph, y + h)
            tall_pair = min(ph, h) > 0.4 * ref
            if gap < 0.12 * ref and (x1 - x0) < 0.9 * ref and tall_pair:
                merged[-1] = (x0, y0, x1 - x0, y1 - y0)
                continue
        merged.append(box)
    return merged


def read_glyphs(binary: np.ndarray) -> list[Glyph]:
    """Classify every component of a one-line binary crop (255 = ink)."""
    boxes = components(binary)
    if not boxes:
        return []
    tall = [b[3] for b in boxes if b[3] > 0.5 * max(bb[3] for bb in boxes)]
    ref = float(np.median(tall)) if tall else float(max(b[3] for b in boxes))
    boxes = _merge_split(boxes, ref)
    # Vertical band of the full-height glyphs: zero and hyphen sit inside it,
    # while letter dots and diacritics sit above or below it.
    tall_boxes = [b for b in boxes if b[3] > 0.6 * ref]
    band_top = float(np.median([b[1] for b in tall_boxes])) if tall_boxes else 0.0
    band_bottom = float(np.median([b[1] + b[3] for b in tall_boxes])) if tall_boxes else float(binary.shape[0])
    band = max(1.0, band_bottom - band_top)
    glyphs: list[Glyph] = []
    for x, y, w, h in boxes:
        if h < 0.18 * ref and w < 0.18 * ref:
            continue  # speck
        centre = (y + h / 2 - band_top) / band
        small = h <= 0.5 * ref
        if small and not 0.2 <= centre <= 0.85:
            glyphs.append(Glyph(x, y, w, h, "?", 0.0))  # a dot of a letter, not a digit
        elif h <= 0.35 * ref and w >= 1.6 * h:
            glyphs.append(Glyph(x, y, w, h, "-", 1.0))
        elif small and 0.5 <= w / max(h, 1) <= 2.0:
            glyphs.append(Glyph(x, y, w, h, "0", 0.9))
        else:
            char, score = classify(binary[y:y + h, x:x + w])
            if w / max(h, 1) < 0.3:
                char, score = "1", max(score, 0.8)
            glyphs.append(Glyph(x, y, w, h, char if score >= _MIN_SCORE else "?", score))
    return glyphs


def number_run(binary: np.ndarray) -> tuple[list[str], int]:
    """Like leftmost_number_run, also returning the run's right x edge
    (0 when no digits were found), so the text part can be cropped apart.

    The run also ends at a wide gap: a colon or a word printed further right
    is not part of the number."""
    groups: list[str] = []
    current = ""
    right = 0
    glyphs = read_glyphs(binary)
    tall = [g.h for g in glyphs if g.char not in "-0?"]
    ref = float(np.median(tall)) if tall else 0.0
    for g in glyphs:
        if g.char == "?":
            break
        if right and ref and g.x - right > 1.4 * ref:
            break
        if g.char == "-":
            if current:
                groups.append(current)
                current = ""
        else:
            current += g.char
        right = g.x + g.w
    if current:
        groups.append(current)
    return groups, (right if groups else 0)


def leftmost_number_run(binary: np.ndarray) -> list[str]:
    """Digit groups (visual left-to-right) from the left end of an RTL line.

    'دمشق ٦-٨-١٩٩٩' is drawn as '١٩٩٩-٨-٦ دمشق', so the number sits at
    the left; reading stops at the first component that is not a digit.
    Returns groups split on hyphens, e.g. ['1983', '8', '6'].
    """
    return number_run(binary)[0]


def read_number(binary: np.ndarray) -> str:
    """All digits in a crop, visual order, unknown glyphs dropped."""
    return "".join(g.char for g in read_glyphs(binary) if g.char.isdigit())
