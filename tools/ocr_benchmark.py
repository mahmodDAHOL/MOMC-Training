"""Measure the ID reader on a folder made by tools/synth_cards.py.

Usage: python tools/ocr_benchmark.py CARD_DIR [LIMIT]
Prints per-field accuracy (exact match after normalising alef/taa forms)
and how often a wrong value was returned with confidence >= 0.8.
"""
import glob
import json
import os
import re
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from momc_training.ocr import syrian_id, text  # noqa: E402

TR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})


def norm(v):
    return re.sub(r"\s+", " ", text.to_latin_digits(text.clean(str(v))).translate(TR)).strip()


def expected(truth, side):
    if side == "front":
        keys = ["first_name", "last_name", "father_name", "mother_name", "birth_place", "birth_date", "national_id"]
        return {k: truth[k] for k in keys}
    return {"governorate": truth["governorate"], "registry": truth["registry"],
            "gender": truth["gender"], "id_issue_date": truth["id_issue_date"]}


def main(folder, limit=None):
    stats = defaultdict(lambda: [0, 0, 0, 0])  # right, empty, wrong, confident-wrong
    sides_ok = [0, 0]
    t0 = time.time()
    files = sorted(glob.glob(os.path.join(folder, "*.json")))[: limit or None]
    for jf in files:
        truth = json.load(open(jf, encoding="utf-8"))
        for side in ("front", "back"):
            data = open(jf.replace(".json", f"_{side}.jpg"), "rb").read()
            got = syrian_id.read_card(data)  # no side hint: detection is measured too
            sides_ok[0] += got["side"] == side
            sides_ok[1] += 1
            for key, want in expected(truth, side).items():
                f = got["fields"].get(key, {}) if got["side"] == side else {}
                value = f.get("value", "")
                if not value:
                    stats[key][1] += 1
                elif norm(value) == norm(want):
                    stats[key][0] += 1
                else:
                    stats[key][2] += 1
                    stats[key][3] += f.get("confidence", 0) >= 0.8
    n = len(files)
    print(f"cards: {n}  sides detected: {sides_ok[0]}/{sides_ok[1]}  time/side: {(time.time() - t0) / max(1, 2 * n):.1f}s")
    print(f"{'field':15} {'correct':>8} {'empty':>6} {'wrong':>6} {'wrong@conf>=.8':>15}")
    for key, (r, e, w, cw) in stats.items():
        print(f"{key:15} {100 * r / n:7.0f}% {e:6d} {w:6d} {cw:15d}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else None)
