"""Build momc_training/ocr/digit_templates.npz from TTF fonts.

Usage: python tools/build_digit_templates.py FONT_DIR [FONT_DIR ...]
Every font that contains Arabic-Indic digits is rendered at two sizes,
with thin/normal/bold stroke variants, and normalised to 32x32.
"""
import glob
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

DIGITS = "٠١٢٣٤٥٦٧٨٩"
S = 32

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from momc_training.ocr.digits import descriptor as norm  # noqa: E402  same descriptor as runtime


def main(dirs):
    X, Y, used = [], [], []
    files = sorted({f for d in dirs for f in glob.glob(os.path.join(d, "*.ttf"))})
    for f in files:
        try:
            probe = ImageFont.truetype(f, 60)
        except OSError:
            continue
        if probe.getmask("٦").getbbox() is None or probe.getmask("٦").getbbox() == probe.getmask("￿").getbbox():
            continue
        used.append(os.path.basename(f))
        for size in (56, 96):
            fnt = ImageFont.truetype(f, size)
            for i, d in enumerate(DIGITS):
                im = Image.new("L", (220, 220), 0)
                ImageDraw.Draw(im).text((60, 40), d, fill=255, font=fnt)
                a = (np.array(im) > 128).astype(np.uint8) * 255
                if a.sum() == 0:
                    continue
                for k in (0, 5, 9, 13):  # stroke weights: font outline to heavy card print
                    v = cv2.dilate(a, np.ones((k, k), np.uint8)) if k else a
                    X.append(norm(v))
                    Y.append(i)
    out = os.path.join(os.path.dirname(__file__), "..", "momc_training", "ocr", "digit_templates.npz")
    np.savez_compressed(out, X=np.array(X, np.float32), Y=np.array(Y, np.int8))
    print(f"{len(X)} templates from {len(used)} fonts:", ", ".join(used))

if __name__ == "__main__":
    main(sys.argv[1:])
