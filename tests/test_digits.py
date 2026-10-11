"""Digit reader on synthetic print, including heavy card-like strokes."""

import glob
import os

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from momc_training.ocr import digits

FONT = next(
    (f for f in glob.glob("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") if os.path.exists(f)), None
)


def render(visual: str, bold: int = 0) -> np.ndarray:
    """Draw glyphs one by one, left to right, so the test controls visual order
    (drawing the whole string would let the bidi engine reorder it)."""
    font = ImageFont.truetype(FONT, 64)
    img = Image.new("L", (60 * len(visual) + 40, 140), 0)
    draw = ImageDraw.Draw(img)
    for i, ch in enumerate(visual):
        draw.text((20 + 60 * i, 20), ch, fill=255, font=font)
    arr = (np.array(img) > 128).astype(np.uint8) * 255
    if bold:
        arr = cv2.dilate(arr, np.ones((bold, bold), np.uint8))
    return arr


@pytest.mark.skipif(FONT is None, reason="DejaVu font not installed")
@pytest.mark.parametrize("bold", [0, 3])
def test_reads_every_digit(bold):
    visual = "٠١٢٣٤٥٦٧٨٩"
    assert digits.read_number(render(visual, bold)) == "0123456789"


@pytest.mark.skipif(FONT is None, reason="DejaVu font not installed")
def test_number_run_splits_on_hyphens():
    groups = digits.leftmost_number_run(render("١٩٨٣-٨-٦"))
    assert groups == ["1983", "8", "6"]
