"""Five fictional contracts written to read like real US hotel supplier paper (data/realistic_hotel): the offline rules read every labelled term.
Each pattern added for them (an end date in a 'Term and Renewal' clause or an order-form row, 'US$' unit prices that are not the annual value,
'not exceed the Annual Contract Price', a data-breach super-cap, 'may not terminate before the end of the term', non-cancellable fees,
the sentence that pays an invoice) is pinned here."""
import json
from pathlib import Path

import pytest

from app import docstruct, extract_rules, kcc
from app.db import SessionLocal
from app.parsing import parse_document

ROOT = Path(__file__).resolve().parents[2] / "data" / "realistic_hotel"
LABELS = json.loads((ROOT / "labels.json").read_text())
SOURCES = {d["file"]: d for d in json.loads((ROOT / "sources.json").read_text())}


def _same(want, got) -> bool:
    if isinstance(want, bool) or want is None:
        return got == want or (want is None and got in (None, ""))
    if isinstance(want, (int, float)):
        return got is not None and abs(float(got) - want) <= 0.01 * max(abs(want), 1)
    return str(got or "")[:10].lower() == str(want)[:10].lower() if "-" in str(want) else str(want).lower() in str(got or "").lower()


@pytest.mark.parametrize("file", sorted(SOURCES))
def test_realistic_contract_terms_are_read(file, monkeypatch):
    monkeypatch.setattr(extract_rules.settings, "customer_names", "Seabright")      # the hotel edition's own company (CUSTOMER_NAMES=Seabright)
    md = docstruct.load_document(ROOT / "docs" / file)         # the delivered PDF / Word file, as the inbox reads it
    with SessionLocal() as s:
        cfg = kcc.load_kcc(s)
    header, clauses = parse_document(md, lambda h, t: kcc.classify(h, t, cfg))
    got = extract_rules.extract(md, header, clauses, SOURCES[file]["type"])
    wrong = {f: (got.get(f, {}).get("value"), want) for f, want in LABELS[file].items() if f != "vendor" and not _same(want, got.get(f, {}).get("value"))}
    assert not wrong, wrong
