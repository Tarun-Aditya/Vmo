import json
from datetime import date

from app.deviations import compare_document, word_diff
from app.docgen.generate import generate
from app.parsing import parse_document


def test_word_diff_marks_changes():
    ops = word_diff("pay within 45 days", "pay within 15 days")
    assert ["del", "45"] in ops and ["ins", "15"] in ops


def test_drafts_find_all_planted_and_clean_control_is_clean(tmp_path):
    generate(tmp_path, date(2026, 11, 6))
    labels = json.loads((tmp_path / "labels.json").read_text())["drafts"]
    man = json.loads((tmp_path / "manifest.json").read_text())["drafts"]
    for d in man:
        _, clauses = parse_document((tmp_path / d["file"]).read_text())
        found = {i["clause_type"]: i for i in compare_document(clauses, d["template"], "heuristic")}
        planted = labels[d["key"]]["deviations"]
        assert {p["clause_type"] for p in planted} == set(found), d["key"]
        for p in planted:
            assert found[p["clause_type"]]["severity"] == p["severity"]
