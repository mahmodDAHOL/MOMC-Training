import glob
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "momc_training", "momc_training", "workspace")


def test_workspace_name_label_title_match():
    """Frappe links the sidebar by title and finds pages by name; they must match."""
    files = glob.glob(os.path.join(ROOT, "*", "*.json"))
    assert files
    for path in files:
        w = json.load(open(path, encoding="utf-8"))
        assert w["name"] == w["label"] == w["title"], path
        folder = os.path.basename(os.path.dirname(path))
        assert folder == w["name"].replace(" ", "_").lower(), path


def test_number_card_blocks_reference_row_labels():
    """Frappe finds a number_card block's widget by the child row's label."""
    for path in glob.glob(os.path.join(ROOT, "*", "*.json")):
        w = json.load(open(path, encoding="utf-8"))
        labels = {row["label"] for row in w["number_cards"]}
        for block in json.loads(w["content"]):
            if block["type"] == "number_card":
                assert block["data"]["number_card_name"] in labels, block
