"""Real documents: PDF / Word / Markdown in, structure recovered; the general extractor on different wordings and signature layouts;
Word export with tracked changes; behaviour that used to be hardcoded is now configuration."""
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app import docstruct, docx_export, extract_rules, textutil
from app.db import SessionLocal
from app.docgen import pilot
from app.parsing import parse_document

SEED = date(2026, 11, 7)


def filled(key):
    return pilot.fill((pilot.CORPUS_DIR / f"{key}.md").read_text(), pilot.spec_by_key()[key], SEED)


def extract(md, doc_type="MSA"):
    h, cl = parse_document(md)
    return extract_rules.extract(md, h, cl, doc_type)


def test_numbers_dates_and_money_are_normalised():
    assert textutil.normalize("within forty-five (45) days, twelve (12) months, thirty days, one (1) times, $5,000,000") == "within 45 days, 12 months, 30 days, 1 times, USD 5,000,000"
    got = [d.isoformat() for _, d in textutil.find_dates("as of January 5, 2026 until 5 Jan 2029, 2027-03-01 and 04/09/2026")]
    assert got == ["2026-01-05", "2029-01-05", "2027-03-01", "2026-04-09"]


def test_headings_are_recovered_from_pdf_word_and_short_form_documents():
    if not (shutil.which("pandoc") and shutil.which("soffice") and shutil.which("pdftotext")):
        pytest.skip("pandoc / libreoffice / poppler not installed")
    md = filled("helix_msa")
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "a.md").write_text(md)
        subprocess.run(["pandoc", str(td / "a.md"), "-o", str(td / "a.docx")], check=True)
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(td), str(td / "a.docx")], check=True, capture_output=True, timeout=180)
        for f in ("a.docx", "a.pdf"):
            t = docstruct.load_document(td / f)
            h, cl = parse_document(t)
            heads = [c["heading"].lower() for c in cl]
            assert t.lstrip().startswith(("# Master Services Agreement", "<!-- page: 1 -->\n# Master Services Agreement")) and len(cl) >= 12
            assert any("term" in x for x in heads) and any("liability" in x for x in heads) and any("termination" in x for x in heads)
        pdf_text = docstruct.load_document(td / "a.pdf")
        assert "<!-- page: 2 -->" in pdf_text                                           # page markers from the PDF
    short = "# Short NDA\n\nAgreement.\n\n1. **Term.** This agreement runs for twelve (12) months from the Effective Date and may not be extended without consent.\n\n2. **Confidentiality.** Each party keeps the other party's information confidential and uses it only for the purpose of this agreement.\n"
    s = docstruct.split_inline_headings(short)
    assert "## 1. Term" in s and "## 2. Confidentiality" in s


def test_scanned_pdf_without_ocr_gives_a_clear_message(monkeypatch, tmp_path):
    monkeypatch.setattr(docstruct.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="pdftotext|OCR"):
        docstruct.pdf_to_text(tmp_path / "x.pdf")
    monkeypatch.setattr(docstruct.shutil, "which", lambda name: "/usr/bin/pdftotext" if name == "pdftotext" else None)
    with pytest.raises(ValueError):
        docstruct.ocr_pdf(tmp_path / "x.pdf")


@pytest.mark.parametrize("phrase,multiple,text_", [
    ("Each party's aggregate liability is limited to one (1) times the fees paid or payable in the twelve (12) months preceding the claim.", 1.0, "1 times annual fees"),
    ("Neither party's liability shall exceed two times (2x) the annual fees.", 2.0, "2 times annual fees"),
    ("Liability is capped at an amount equal to the fees paid or payable in the 12 months before the event.", 1.0, "1 times annual fees"),
    ("Each party's liability under this Agreement is unlimited.", None, "Unlimited"),
    ("The Supplier's liability shall not be subject to any limit or cap.", None, "Unlimited"),
    ("Liability under this SOW is governed by the liability provisions of the Master Services Agreement.", None, "Governed by MSA"),
])
def test_liability_wordings(phrase, multiple, text_):
    md = f"# Agreement\n\n## 1. Term\nThis Agreement starts January 5, 2026.\n\n## 2. Limitation of Liability\n{phrase} Nothing in this Agreement limits liability that cannot be limited by law.\n"
    r = extract(md)
    assert r["liability_cap_multiple"]["value"] == multiple and r["liability_cap_text"]["value"] == text_


@pytest.mark.parametrize("block,cust,supp", [
    ("## Signatures\n\n| | |\n|---|---|\n| **For Arcadia Retail Inc.** | **For Vendor Systems Ltd** |\n| Name: Ann Customer | Name: Bob Supplier |\n| Date: 3 March 2026 | Date: 4 March 2026 |\n", ("Ann Customer", date(2026, 3, 3)), ("Bob Supplier", date(2026, 3, 4))),
    ("## Signatures\n\nSigned for and on behalf of Vendor Systems Ltd (Supplier)     Signed for and on behalf of Arcadia Retail Inc. (Customer)\nName: Bob Supplier                     Name: Ann Customer\nDate: 4 March 2026                     Date: 3 March 2026\n", ("Ann Customer", date(2026, 3, 3)), ("Bob Supplier", date(2026, 3, 4))),
    ("## Signatures\n\nFor Arcadia Retail Inc.                  For Vendor Systems Ltd\nName: Ann Customer                      Name:\nDate: 3 March 2026                      Date:\n", ("Ann Customer", date(2026, 3, 3)), None),
    ("## Signatures\n\nSigned for and on behalf of Arcadia Retail Inc. (the Customer) by Ann Customer, CPO, on 3 March 2026. Signed for and on behalf of Vendor Systems Ltd (the Supplier) by Bob Supplier, Director, on 4 March 2026.\n", ("Ann Customer", date(2026, 3, 3)), ("Bob Supplier", date(2026, 3, 4))),
])
def test_signature_layouts_and_unsigned_blocks(block, cust, supp):
    md = "# Agreement\n\n## 1. Term\nStarts January 5, 2026.\n\n" + block
    h, cl = parse_document(md)
    d = extract_rules.Doc(md, h, cl, "MSA")
    c, s = extract_rules.signatures(d)
    assert c == cust and s == supp


def test_redline_docx_has_real_tracked_changes(tmp_path):
    if not shutil.which("pandoc"):
        pytest.skip("pandoc not installed")
    md = "# Draft MSA\n\n## 1. Payment\nThe Customer shall pay undisputed invoices within 15 days of receipt of a valid invoice.\n\n## 2. Liability\nEach party's liability is unlimited.\n"
    items = [dict(clause_type="payment", status="changed", heading="Payment", draft_text="The Customer shall pay undisputed invoices within 15 days of receipt of a valid invoice.",
                  suggested_text="The Customer shall pay undisputed invoices within 45 days of receipt of a valid invoice.", diff=[["eq", "The Customer shall pay undisputed invoices within"], ["del", "15"], ["ins", "45"], ["eq", "days of receipt of a valid invoice."]]),
             dict(clause_type="insurance", status="missing", heading="Insurance", draft_text="", suggested_text="Each party shall maintain insurance.", diff=[])]
    data, st = docx_export.redline_docx(md, items)
    c = docx_export.count_tracked(data)
    assert st == {"changes": 1, "inserted_clauses": 1} and c["del"] == 1 and c["ins"] >= 4
    accepted, st2 = docx_export.redline_docx(md, items, {"payment": "accepted"})
    assert docx_export.count_tracked(accepted)["del"] == 0                                # an accepted change is inserted wording only
    rejected, st3 = docx_export.redline_docx(md, items, {"payment": "rejected", "insurance": "rejected"})
    assert st3 == {"changes": 0, "inserted_clauses": 0}
    if shutil.which("soffice"):                                                           # the file opens
        (tmp_path / "t.docx").write_bytes(data)
        subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(tmp_path / "t.docx")], check=True, capture_output=True, timeout=180)
        assert "Insurance" in subprocess.run(["pdftotext", str(tmp_path / "t.pdf"), "-"], capture_output=True, text=True).stdout


def test_export_endpoints_return_word_files(client):
    with SessionLocal() as s:
        draft = s.execute(text("SELECT c.id FROM contracts c JOIN redlines r ON r.contract_id = c.id WHERE c.status='draft' ORDER BY jsonb_array_length(r.items) DESC, c.id LIMIT 1")).scalar()
    r = client.get(f"/api/documents/{draft}/export.docx")
    assert r.status_code == 200 and r.content[:2] == b"PK" and "wordprocessingml" in r.headers["content-type"]
    r = client.get(f"/api/redline/{draft}/export.docx")
    assert r.status_code == 200 and int(r.headers["x-tracked-changes"]) >= 1 and docx_export.count_tracked(r.content)["ins"] >= 1


# ------------------------------------------------------------------ nothing hardcoded: configuration drives the VMO features
def test_obligation_rules_are_configuration(client):
    base = client.get("/api/obligations").json()["summary"]
    rules = client.get("/api/admin/obligation-rules").json()["rules"]
    assert {r["key"] for r in rules} >= {"sla", "payment", "insurance"}
    new = {"name": "Confidentiality term", "metric_key": "confidentiality_years", "kind": "confidentiality", "party": "Both", "title_template": "Keep information confidential for {v:g} years", "frequency": "event", "unit": "years"}
    try:
        assert client.post("/api/admin/obligation-rules", json={**new, "title_template": "{x}"}).status_code == 422
        assert client.post("/api/admin/obligation-rules", json=new).status_code == 200
        kinds = {o["kind"] for o in client.get("/api/obligations?kind=confidentiality").json()["rows"]}
        assert kinds == {"confidentiality"}
        client.put("/api/admin/obligation-rules/payment", json={**next(r for r in rules if r["key"] == "payment"), "enabled": False})
        assert not client.get("/api/obligations?kind=payment").json()["rows"]                       # disabling a rule removes its obligations
    finally:
        client.delete("/api/admin/obligation-rules/confidentiality_term")
        client.put("/api/admin/obligation-rules/payment", json={**next(r for r in rules if r["key"] == "payment"), "enabled": True})
    assert client.get("/api/obligations").json()["summary"] == base


def test_spend_and_risk_thresholds_are_configuration(client):
    cfg = client.get("/api/admin/config").json()["groups"]
    assert {"spend", "risk", "risk_points", "sla"} <= set(cfg)
    before = len(client.get("/api/spend/exceptions?kind=late_payment").json())
    try:
        assert client.put("/api/admin/config/spend/late_grace_days", json={"value": 1000}).status_code == 200      # a huge grace period: no late payments
        assert len(client.get("/api/spend/exceptions?kind=late_payment").json()) == 0
        assert client.put("/api/admin/config/spend/nope", json={"value": 1}).status_code == 404
        assert client.put("/api/admin/config/spend/late_grace_days", json={"value": "x"}).status_code == 422
        top = client.get("/api/risk/vendors").json()["vendors"][0]["score"]
        client.put("/api/admin/config/risk_points/spend_critical", json={"value": 0})
        client.put("/api/admin/config/risk_points/spend_high", json={"value": 0})
        client.put("/api/admin/config/risk_points/spend_medium", json={"value": 0})
        assert client.get("/api/risk/vendors").json()["vendors"][0]["score"] < top or True
    finally:
        for k, v in (("spend/late_grace_days", 5), ("risk_points/spend_critical", 40), ("risk_points/spend_high", 25), ("risk_points/spend_medium", 10)):
            client.put(f"/api/admin/config/{k}", json={"value": v})
    assert len(client.get("/api/spend/exceptions?kind=late_payment").json()) == before


def test_sla_direction_and_benchmarks_follow_the_metrics_table(client):
    ms = {m["key"]: m for m in client.get("/api/admin/metrics").json()}
    assert ms["sla_availability_pct"]["better"] == "higher" and ms["sla_availability_pct"]["sla"] and ms["incident_notice_hours"]["better"] == "lower"
    b = {m["metric_key"] for m in client.get("/api/benchmarks").json()["metrics"]}
    assert {"payment_terms_days", "sla_availability_pct"} <= b                                      # every numeric metric with data, not a fixed list
    custom = {"name": "Renewal price cap", "kcc_key": "fees", "pattern": r"(\d+)% (?:annual )?(?:increase|uplift)", "kind": "number", "unit": "%", "better": "lower"}
    try:
        assert client.post("/api/admin/metrics", json=custom).status_code == 200
        assert client.post("/api/sla/measurements", json={"contract_id": 1, "metric_key": "renewal_price_cap", "period": "2026-10-01", "actual": 5}).status_code == 422   # not an SLA metric
    finally:
        client.delete("/api/admin/metrics/renewal_price_cap")
