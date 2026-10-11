"""End-to-end reader check on generated cards (needs tesseract + ara model)."""

import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

pytesseract = pytest.importorskip("pytesseract")
if not shutil.which("tesseract") or "ara" not in pytesseract.get_languages(config=""):
    pytest.skip("tesseract with the Arabic model is not installed", allow_module_level=True)

import synth_cards  # noqa: E402
from ocr_benchmark import expected, norm  # noqa: E402

from momc_training.ocr import syrian_id  # noqa: E402

SEEDS = (11, 22, 33)


@pytest.mark.parametrize("seed", SEEDS)
def test_reads_generated_card(seed):
    truth, front, back = synth_cards.make(seed)
    hits, total = 0, 0
    for side, data in (("front", front), ("back", back)):
        got = syrian_id.read_card(data)  # no hint: side detection is part of the test
        assert got["side"] == side
        for key, want in expected(truth, side).items():
            field = got["fields"].get(key, {})
            total += 1
            hits += norm(field.get("value", "")) == norm(want)
            # A value read with high confidence must be right.
            if field.get("confidence", 0) >= 0.85 and key in ("national_id", "birth_date", "id_issue_date"):
                assert norm(field["value"]) == norm(want), key
    assert hits / total >= 0.5
