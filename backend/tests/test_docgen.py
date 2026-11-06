import json
from datetime import date

from app.docgen.generate import generate, inr
from app.extraction import heuristic_extract
from app.parsing import parse_document

SEED = date(2026, 11, 6)


def test_inr_grouping():
    assert inr(4800000) == "48,00,000" and inr(36_00_000) == "36,00,000" and inr(950) == "950"


def gen(tmp_path):
    generate(tmp_path, SEED)
    return (json.loads((tmp_path / "labels.json").read_text()),
            json.loads((tmp_path / "manifest.json").read_text()))


def test_document_set_shape(tmp_path):
    labels, man = gen(tmp_path)
    assert (len(man["templates"]), len(man["contracts"]), len(man["drafts"])) == (5, 18, 5)
    types = [c["type"] for c in man["contracts"]]
    assert {t: types.count(t) for t in set(types)} == {
        "MSA": 2, "SOW": 5, "Amendment": 2, "SaaS": 4, "NDA": 3, "DPA": 2}


def test_planted_facts(tmp_path):
    labels, man = gen(tmp_path)
    c = {k: v for k, v in labels["contracts"].items() if "_amd" not in k}
    days = {k: (date.fromisoformat(v["expiry_date"]) - SEED).days for k, v in c.items()}
    # effective expiry: amendments extend the two MSAs
    days["bluepeak_msa"] = (date.fromisoformat(labels["contracts"]["bluepeak_amd1"]["expiry_date"]) - SEED).days
    days["meridian_msa"] = (date.fromisoformat(labels["contracts"]["meridian_amd1"]["expiry_date"]) - SEED).days
    assert sum(d <= 30 for d in days.values()) == 4
    assert sum(30 < d <= 90 for d in days.values()) == 4
    assert sum(d > 365 for d in days.values()) == 8
    assert sum(v["auto_renew"] for v in c.values()) == 5
    assert sum(v["liability_cap_text"] == "Unlimited" for v in c.values()) == 3
    assert sum(v["termination_for_convenience"] is False for v in c.values()) == 2
    saas_pd_no_dpa = [k for k, v in c.items() if v["processes_personal_data"] and not v["has_dpa"]]
    assert saas_pd_no_dpa == ["pulsehr"]
    drafts = labels["drafts"]
    assert sorted(len(d["deviations"]) for d in drafts.values()) == [0, 3, 4, 5, 6]


def test_extraction_matches_labels(tmp_path):
    labels, man = gen(tmp_path)
    for m in man["contracts"]:
        header, clauses = parse_document((tmp_path / "docs" / m["file"]).read_text())
        got = heuristic_extract(header, clauses, m["type"])
        for f, want in labels["contracts"][m["key"]].items():
            if f == "deviations":
                continue
            assert got[f]["value"] == want, (m["key"], f)


def test_page_markers_and_clause_split(tmp_path):
    gen(tmp_path)
    _, clauses = parse_document((tmp_path / "docs/contracts/pulsehr.md").read_text())
    assert len(clauses) == 14 and clauses[0]["page"] == 1 and clauses[-1]["page"] == 5
    assert all(c["clause_type"] != "other" for c in clauses)
