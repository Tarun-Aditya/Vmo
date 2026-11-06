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
    return (
        json.loads((tmp_path / "labels.json").read_text()),
        json.loads((tmp_path / "manifest.json").read_text()),
    )


def test_document_set_shape(tmp_path):
    labels, man = gen(tmp_path)
    assert (len(man["templates"]), len(man["contracts"]), len(man["drafts"])) == (6, 21, 5)
    types = [c["type"] for c in man["contracts"]]
    assert {t: types.count(t) for t in set(types)} == {
        "MSA": 2,
        "SOW": 5,
        "Work Order": 3,
        "Amendment": 2,
        "SaaS": 4,
        "NDA": 3,
        "DPA": 2,
    }


def test_planted_facts(tmp_path):
    labels, man = gen(tmp_path)
    c = {k: v for k, v in labels["contracts"].items() if "_amd" not in k}
    days = {k: (date.fromisoformat(v["expiry_date"]) - SEED).days for k, v in c.items()}
    # effective expiry: amendments extend the two MSAs
    days["bluepeak_msa"] = (
        date.fromisoformat(labels["contracts"]["bluepeak_amd1"]["expiry_date"]) - SEED
    ).days
    days["meridian_msa"] = (
        date.fromisoformat(labels["contracts"]["meridian_amd1"]["expiry_date"]) - SEED
    ).days
    assert sum(d <= 30 for d in days.values()) == 4
    assert sum(30 < d <= 90 for d in days.values()) == 4
    assert sum(d > 365 for d in days.values()) == 11  # 8 + 3 work orders
    assert sum(v["auto_renew"] for v in c.values()) == 5
    assert sum(v["liability_cap_text"] == "Unlimited" for v in c.values()) == 3
    assert sum(v["termination_for_convenience"] is False for v in c.values()) == 2
    unsigned = [k for k, v in c.items() if v["fully_executed"] is False]
    assert unsigned == ["bluepeak_wo2"]  # planted: supplier has not countersigned
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


def test_templates_are_typical_and_children_build_on_parents(tmp_path):
    from app.docgen.library import TEMPLATES

    assert len(TEMPLATES["MSA"]["clauses"]) == 21 and len(TEMPLATES["SOW"]["clauses"]) == 15
    for needed in ("order_of_precedence", "warranties", "insurance", "force_majeure", "dispute_resolution"):
        assert needed in TEMPLATES["MSA"]["clauses"]
    assert {"key_personnel", "governance", "deliverables", "msa_reference"} <= set(TEMPLATES["SOW"]["clauses"])
    assert {"sow_reference", "order_of_precedence"} <= set(TEMPLATES["WO"]["clauses"])
    gen(tmp_path)
    sow = (tmp_path / "docs/contracts/meridian_sow1.md").read_text()
    assert "issued under the Master Services Agreement dated 2 " in sow and "Meridian Logistics" in sow
    wo = (tmp_path / "docs/contracts/bluepeak_wo1.md").read_text()
    assert "issued under SOW 2 – Managed Network" in wo and "Master Services Agreement dated" in wo
    assert "the Master Services Agreement prevails over this SOW" in (
        tmp_path / "docs/contracts/bluepeak_sow2.md").read_text()
    # planted: this SOW overrides the MSA instead
    assert "this SOW prevails over the Master Services Agreement" in sow


def test_page_markers_and_clause_split(tmp_path):
    gen(tmp_path)
    _, clauses = parse_document((tmp_path / "docs/contracts/pulsehr.md").read_text())
    assert len(clauses) == 15 and clauses[0]["page"] == 1 and clauses[-1]["page"] == 6
    assert clauses[-1]["clause_type"] == "execution" and "Lakshmi Rao" in clauses[-1]["text"]
    assert all(c["clause_type"] != "other" for c in clauses)
