"""Invoices, service-level reports and acceptance certificates are read from documents (three layouts, three formats, scans) and drive spend / SLA / obligation screens."""
import json
import shutil
import subprocess
from datetime import date

import pytest
from sqlalchemy import text

from app import feeds, opsdocs
from app.config import data_path
from app.db import SessionLocal
from app.docgen import ops_fixtures as fx


def row(**kw):
    base = dict(vendor="Quill Staffing Group Ltd", contract_title="Statement of Work No. 2 – Quill Staffing", invoice_no="QUI-2610-007", invoice_date=date(2026, 10, 28), due_date=date(2026, 12, 12),
                paid_date=None, period_start=date(2026, 10, 1), period_end=date(2026, 10, 31), amount=48250.5, description="Contract staffing, October 2026")
    return {**base, **kw}


@pytest.mark.parametrize("style", [0, 1, 2])
def test_each_invoice_layout_is_read(style, tmp_path):
    r = row(paid_date=date(2026, 11, 3) if style == 1 else None)
    f = tmp_path / "inv.md"
    f.write_text(fx.invoice_md(r, style))
    kind, [got] = opsdocs.read(f)
    assert kind == "invoice" and got["invoice_no"] == r["invoice_no"] and got["amount"] == 48250.5 and got["vendor"] == r["vendor"]
    assert got["invoice_date"] == r["invoice_date"] and got["due_date"] == r["due_date"] and got["paid_date"] == r["paid_date"]
    assert "Statement of Work No. 2" in got["contract_title"]


def test_word_and_pdf_versions_read_the_same(tmp_path):
    if not (shutil.which("pandoc") and shutil.which("soffice")):
        pytest.skip("pandoc / libreoffice missing")
    md = tmp_path / "a.md"
    md.write_text(fx.invoice_md(row(), 0))
    subprocess.run(["pandoc", str(md), "-o", str(tmp_path / "a.docx")], check=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(tmp_path / "a.docx")], check=True, capture_output=True, timeout=180)
    a, b, c = (opsdocs.read(tmp_path / n)[1][0] for n in ("a.md", "a.docx", "a.pdf"))
    for k in ("invoice_no", "amount", "invoice_date", "due_date", "vendor"):
        assert a[k] == b[k] == c[k], k


def test_scanned_invoice_is_read_by_ocr(tmp_path):
    if not all(shutil.which(x) for x in ("tesseract", "pdftoppm", "pandoc", "soffice", "convert")):
        pytest.skip("OCR tools missing")
    (tmp_path / "a.md").write_text(fx.invoice_md(row(), 0))
    subprocess.run(["pandoc", str(tmp_path / "a.md"), "-o", str(tmp_path / "a.docx")], check=True)
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(tmp_path), str(tmp_path / "a.docx")], check=True, capture_output=True, timeout=180)
    subprocess.run(["pdftoppm", "-r", "150", "-png", str(tmp_path / "a.pdf"), str(tmp_path / "pg")], check=True)
    subprocess.run(["convert", *sorted(map(str, tmp_path.glob("pg*.png"))), "-colorspace", "Gray", "-rotate", "0.5", "-blur", "0x0.5", str(tmp_path / "scan.pdf")], check=True)
    assert subprocess.run(["pdftotext", str(tmp_path / "scan.pdf"), "-"], capture_output=True, text=True).stdout.strip() == ""
    kind, [got] = opsdocs.read(tmp_path / "scan.pdf")
    assert kind == "invoice" and got["invoice_no"] == "QUI-2610-007" and got["amount"] == 48250.5 and got["due_date"] == date(2026, 12, 12)


def test_unrecognised_document_is_refused(tmp_path):
    f = tmp_path / "memo.md"
    f.write_text("# Lunch menu\n\nSoup and salad. Price USD 12.")
    with pytest.raises(ValueError):
        opsdocs.read(f)


def test_every_fixture_document_is_read_back_correctly(seeded):
    """Scored against labels_ops.json (written from the fixture rows): the readers must get >= 97% of fields right."""
    lab = json.loads((data_path() / "labels_ops.json").read_text())
    root = data_path() / "feeds"
    ok = tot = 0
    for fn, want in lab["invoices"].items():
        _, [got] = opsdocs.read(next(root.rglob(fn)))
        for f in ("invoice_no", "invoice_date", "due_date", "paid_date"):
            tot += 1
            ok += (str(got.get(f)) if got.get(f) else None) == (want.get(f) or None)
        tot += 2
        ok += abs(float(got["amount"]) - float(want["amount"])) < 0.01
        ok += got["vendor"] == want["vendor"]
    for fn, want in lab["sla"].items():
        _, rows = opsdocs.read(next(root.rglob(fn)))
        tot += 1
        ok += {(r["metric_key"], round(r["actual"], 2), r["incidents"]) for r in rows} == {(r["metric_key"], round(float(r["actual"]), 2), int(r["incidents"])) for r in want["rows"]}
    assert tot > 300 and ok / tot >= 0.97, f"{ok}/{tot}"


def test_a_dropped_invoice_lands_on_its_contract_and_is_idempotent(seeded):
    with SessionLocal() as s:
        c = s.execute(text("SELECT id, title, vendor FROM contracts WHERE status<>'draft' AND type='SaaS' LIMIT 1")).mappings().first()
        before = s.execute(text("SELECT count(*) FROM invoices")).scalar()
    f = data_path() / "feeds" / "invoices" / "zz_dropped.md"
    f.write_text(fx.invoice_md(row(vendor=c["vendor"], contract_title=c["title"], invoice_no="ZZ-9001", amount=12345.0), 0))
    try:
        r1 = feeds.run_feeds("manual")
        r2 = feeds.run_feeds("manual")
        with SessionLocal() as s:
            i = s.execute(text("SELECT contract_id, amount, vendor FROM invoices WHERE invoice_no='ZZ-9001'")).mappings().all()
            after = s.execute(text("SELECT count(*) FROM invoices")).scalar()
        assert r1["failed"] == 0 and len(i) == 1 and i[0]["contract_id"] == c["id"] and float(i[0]["amount"]) == 12345.0
        assert after == before + 1 and r2["new_docs"] == 0
    finally:
        f.unlink()
        with SessionLocal() as s:
            s.execute(text("DELETE FROM invoices WHERE invoice_no='ZZ-9001'"))
            s.commit()
        feeds.recompute()
