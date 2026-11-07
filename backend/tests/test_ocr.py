"""Scanned contracts: an image-only PDF (clean and noisy / skewed) goes through OCR and yields the same key fields as the digital original."""
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

import pytest

from app import docstruct, kcc
from app.docgen import pilot
from app.extract_rules import extract
from app.parsing import parse_document

NEED = ["tesseract", "pdftoppm", "pandoc", "soffice", "convert"]
pytestmark = pytest.mark.skipif(any(shutil.which(x) is None for x in NEED), reason="needs tesseract, poppler, pandoc, libreoffice, imagemagick")
FIELDS = ["effective_date", "expiry_date", "governing_law", "payment_terms_days", "auto_renew", "customer_signatory", "supplier_signatory"]


def _run(*a):
    subprocess.run(list(a), check=True, capture_output=True, timeout=240)


@pytest.fixture(scope="module")
def pdfs():
    md = pilot.fill((pilot.CORPUS_DIR / "quill_nda.md").read_text(), pilot.spec_by_key()["quill_nda"], date(2026, 11, 7))
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "a.md").write_text(md)
        _run("pandoc", str(t / "a.md"), "-o", str(t / "a.docx"))
        _run("soffice", "--headless", "--convert-to", "pdf", "--outdir", td, str(t / "a.docx"))
        _run("pdftoppm", "-r", "150", "-png", str(t / "a.pdf"), str(t / "pg"))
        pages = sorted(str(p) for p in t.glob("pg*.png"))
        _run("convert", *pages, "-colorspace", "Gray", str(t / "clean.pdf"))
        _run("convert", *pages, "-colorspace", "Gray", "-rotate", "0.6", "-attenuate", "0.15", "+noise", "Gaussian", "-blur", "0x0.6", str(t / "noisy.pdf"))
        yield {"digital": t / "a.pdf", "clean": t / "clean.pdf", "noisy": t / "noisy.pdf"}


def fields(path: Path) -> dict:
    md = docstruct.load_document(path)
    header, clauses = parse_document(md, lambda h, t: kcc.classify(h, t, []))
    out = extract(md, header, clauses, "NDA")
    return {f: out.get(f, {}).get("value") for f in FIELDS}


def test_scans_have_no_text_layer_and_ocr_recovers_the_contract(pdfs):
    assert subprocess.run(["pdftotext", str(pdfs["clean"]), "-"], capture_output=True, text=True).stdout.strip() == ""      # truly image-only
    want = fields(pdfs["digital"])
    assert want["effective_date"] and want["governing_law"]
    for kind in ("clean", "noisy"):
        got = fields(pdfs[kind])
        miss = {f: (got[f], want[f]) for f in FIELDS if got[f] != want[f]}
        assert len(miss) <= 1, f"{kind} scan: {miss}"                      # OCR may mangle at most one value

