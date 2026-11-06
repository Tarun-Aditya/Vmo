import json
from datetime import date

from app.docgen.generate import generate, inr
from app.docgen.library import TEMPLATES
from app.extraction import heuristic_extract
from app.parsing import parse_document

SEED = date(2026, 11, 6)


def test_usd_grouping():
    assert inr(4800000) == "4,800,000" and inr(540000) == "540,000" and inr(950) == "950"


def gen(tmp_path):
    generate(tmp_path, SEED)
    return (json.loads((tmp_path / "labels.json").read_text()), json.loads((tmp_path / "manifest.json").read_text()))


def test_document_set_shape_and_layout(tmp_path):
    labels, man = gen(tmp_path)
    assert (len(man["templates"]), len(man["contracts"]), len(man["drafts"])) == (6, 27, 5)
    types = [c["type"] for c in man["contracts"]]
    assert {t: types.count(t) for t in set(types)} == {"MSA": 3, "SOW": 7, "Work Order": 4, "Amendment": 2, "SaaS": 5, "NDA": 4, "DPA": 2}
    # everything lands in a watched folder with a sidecar, exactly as a dropped document would
    assert len(list((tmp_path / "inbox/contracts").glob("*.md"))) == 27 and len(list((tmp_path / "inbox/drafts").glob("*.md"))) == 5
    assert (tmp_path / "inbox/contracts/accentia_msa.meta.json").exists() and (tmp_path / "templates/template_wo.md").exists()


def test_corpus_is_usd_and_it_services_flavoured(tmp_path):
    gen(tmp_path)
    corpus = "\n".join(p.read_text() for p in (tmp_path / "inbox").rglob("*.md"))
    assert "INR" not in corpus and "crore" not in corpus and "USD" in corpus
    for name in ("Accentia Technology Services", "Delmont Consulting", "Taraka Consultancy Services", "Nginova Systems"):
        assert name in corpus
    assert "SAP S/4HANA" in corpus and "AWS Cloud Migration" in corpus and "Application Managed Services" in corpus


def test_planted_facts(tmp_path):
    labels, man = gen(tmp_path)
    c = {k: v for k, v in labels["contracts"].items() if "_amd" not in k}
    days = {k: (date.fromisoformat(v["expiry_date"]) - SEED).days for k, v in c.items()}
    for msa, amd in (("accentia_msa", "accentia_amd1"), ("delmont_msa", "delmont_amd1")):  # amendments extend the MSAs
        days[msa] = (date.fromisoformat(labels["contracts"][amd]["expiry_date"]) - SEED).days
    assert sum(d <= 30 for d in days.values()) == 4
    assert sum(30 < d <= 90 for d in days.values()) == 4
    assert sum(d > 365 for d in days.values()) == len(days) - 8
    assert sum(v["auto_renew"] for v in c.values()) == 5
    assert sum(v["liability_cap_text"] == "Unlimited" for v in c.values()) == 3
    assert sum(v["termination_for_convenience"] is False for v in c.values()) == 2
    assert [k for k, v in c.items() if v["fully_executed"] is False] == ["accentia_wo2"]
    assert [k for k, v in c.items() if v["processes_personal_data"] and not v["has_dpa"]] == ["pulsehr"]
    assert sum(v["annual_value"] or 0 for v in c.values()) == 38_070_000
    assert sorted(len(d["deviations"]) for d in labels["drafts"].values()) == [0, 3, 4, 5, 6]


def test_extraction_matches_labels(tmp_path):
    labels, man = gen(tmp_path)
    for m in man["contracts"]:
        header, clauses = parse_document((tmp_path / m["file"]).read_text())
        got = heuristic_extract(header, clauses, m["type"])
        for f, want in labels["contracts"][m["key"]].items():
            if f == "deviations":
                continue
            assert got[f]["value"] == want, (m["key"], f)


def test_templates_are_typical_and_children_build_on_parents(tmp_path):
    assert len(TEMPLATES["MSA"]["clauses"]) == 21 and len(TEMPLATES["SOW"]["clauses"]) == 15 and len(TEMPLATES["WO"]["clauses"]) == 10
    for needed in ("order_of_precedence", "warranties", "insurance", "force_majeure", "dispute_resolution"):
        assert needed in TEMPLATES["MSA"]["clauses"]
    gen(tmp_path)
    sow = (tmp_path / "inbox/contracts/delmont_sow1.md").read_text()
    assert "issued under the Master Services Agreement dated 2 " in sow and "Delmont Consulting" in sow
    wo = (tmp_path / "inbox/contracts/accentia_wo1.md").read_text()
    assert "issued under SOW 2 – AWS Cloud Migration" in wo and "Master Services Agreement dated" in wo
    assert "this SOW prevails over the Master Services Agreement" in sow  # planted on Delmont SOW 1


def test_page_markers_and_clause_split(tmp_path):
    gen(tmp_path)
    _, clauses = parse_document((tmp_path / "inbox/contracts/pulsehr.md").read_text())
    assert len(clauses) == 15 and clauses[0]["page"] == 1 and clauses[-1]["page"] == 6
    assert clauses[-1]["clause_type"] == "execution" and "Lakshmi Rao" in clauses[-1]["text"]
    assert all(c["clause_type"] != "other" for c in clauses)
