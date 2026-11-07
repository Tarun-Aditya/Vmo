"""Scanned-contract parity: render pilot contracts to PDF, turn them into noisy image-only scans, OCR them, and compare the extracted fields with the digital original.
Run with LLM_PROVIDER=offline or unset (Claude). Needs tesseract, poppler, pandoc, libreoffice, imagemagick."""
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

from app import docstruct, extraction, kcc
from app.docgen import pilot
from app.parsing import parse_document

KEYS = ["quill_nda", "bluepeak_saas", "helix_sow1"]
FIELDS = ["effective_date", "expiry_date", "governing_law", "payment_terms_days", "auto_renew", "annual_value", "customer_signatory", "supplier_signatory", "liability_cap_multiple", "termination_for_convenience"]


def run(*a):
    subprocess.run(list(a), check=True, capture_output=True, timeout=300)


def fields(path: Path, dtype: str) -> dict:
    md = docstruct.load_document(path)
    header, clauses = parse_document(md, lambda h, t: kcc.classify(h, t, []))
    out, mode = extraction.extract(md, header, clauses, dtype)
    return {f: (out.get(f) or {}).get("value") for f in FIELDS} | {"_mode": mode}


def main() -> int:
    specs = pilot.spec_by_key()
    ok = tot = 0
    for k in KEYS:
        md = pilot.fill((pilot.CORPUS_DIR / f"{k}.md").read_text(), specs[k], date.today())
        with tempfile.TemporaryDirectory() as td:
            t = Path(td)
            (t / "a.md").write_text(md)
            run("pandoc", str(t / "a.md"), "-o", str(t / "a.docx"))
            run("soffice", "--headless", "--convert-to", "pdf", "--outdir", td, str(t / "a.docx"))
            run("pdftoppm", "-r", "150", "-png", str(t / "a.pdf"), str(t / "pg"))
            run("convert", *sorted(map(str, t.glob("pg*.png"))), "-colorspace", "Gray", "-rotate", "0.6", "-attenuate", "0.15", "+noise", "Gaussian", "-blur", "0x0.6", str(t / "scan.pdf"))
            dtype = specs[k]["type"]
            want, got = fields(t / "a.pdf", dtype), fields(t / "scan.pdf", dtype)
        diff = {f: (got[f], want[f]) for f in FIELDS if str(got[f]) != str(want[f])}
        ok += len(FIELDS) - len(diff)
        tot += len(FIELDS)
        print(f"{'PASS' if not diff else 'DIFF'} [{got['_mode']}] {k}: {len(FIELDS) - len(diff)}/{len(FIELDS)} fields same as the digital original {diff or ''}")
    print(f"OVERALL {ok}/{tot} = {100 * ok / tot:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
