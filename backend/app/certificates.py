"""Compliance certificates: what each vendor's contract obliges it to hold (insurance, food safety, statutory inspections, payment-card attestation) and when
the copy on file runs out. A clause only says a certificate is required; the expiry date lives on the certificate itself, so it is recorded by a person
(PATCH /api/certificates/{id}) or loaded from `feeds/certificates.csv` (vendor, kind, expiry_date, received_on, reference), never guessed from the contract."""
from __future__ import annotations

import csv
from datetime import date

from sqlalchemy import text

from app.config import data_path

# clause type -> the certificate that clause obliges the supplier to hold
REQUIRED = {
    "insurance": "Insurance certificate",
    "food_safety": "Food-safety certification (HACCP)",
    "inspection_certificates": "Statutory inspection certificate",
    "payment_card_data": "PCI DSS attestation of compliance",
}
SOON_DAYS = 60


def status(expiry: date | None, today: date | None = None) -> str:
    today = today or date.today()
    if not expiry:
        return "missing"
    return "expired" if expiry < today else "expiring" if (expiry - today).days <= SOON_DAYS else "valid"


def sync(s) -> int:
    """Rebuild the list of required certificates from the clauses of executed contracts. What a person recorded (dates, reference, note) is kept."""
    need = s.execute(text("""SELECT DISTINCT ON (c.vendor, cl.clause_type) c.vendor, cl.clause_type, c.id, cl.page
                             FROM clauses cl JOIN contracts c ON c.id = cl.contract_id
                             WHERE c.status <> 'draft' AND cl.clause_type = ANY(:k)
                             ORDER BY c.vendor, cl.clause_type, (c.parent_id IS NOT NULL), c.id"""), {"k": list(REQUIRED)}).all()
    for vendor, kind, cid, page in need:
        s.execute(text("""INSERT INTO certificates (vendor, kind, name, contract_id, clause_type, page) VALUES (:v, :k, :n, :c, :k, :p)
                          ON CONFLICT (vendor, kind) DO UPDATE SET contract_id = EXCLUDED.contract_id, page = EXCLUDED.page, name = EXCLUDED.name"""),
                  {"v": vendor, "k": kind, "n": REQUIRED[kind], "c": cid, "p": page})
    keep = {(v, k) for v, k, _, _ in need}
    for cid, vendor, kind in s.execute(text("SELECT id, vendor, kind FROM certificates WHERE expiry_date IS NULL AND received_on IS NULL AND note IS NULL")).all():
        if (vendor, kind) not in keep:          # the contract that required it is gone and nothing was ever recorded
            s.execute(text("DELETE FROM certificates WHERE id = :i"), {"i": cid})
    f = data_path() / "feeds" / "certificates.csv"
    if f.exists():
        with f.open(newline="") as fh:
            for r in csv.DictReader(fh):
                s.execute(text("""UPDATE certificates SET expiry_date = :e, received_on = :r, reference = :ref, source = 'file', updated_at = now()
                                  WHERE vendor = :v AND kind = :k AND source <> 'person'"""),
                          {"v": r["vendor"], "k": r["kind"], "e": r.get("expiry_date") or None, "r": r.get("received_on") or None, "ref": r.get("reference") or None})
    return len(need)


def listing(s, today: date | None = None) -> dict:
    today = today or date.today()
    rows = [dict(r) for r in s.execute(text("""SELECT ce.id, ce.vendor, ce.kind, ce.name, ce.contract_id, c.title AS contract_title, ce.page, ce.expiry_date, ce.received_on,
                                                      ce.reference, ce.note, ce.source,
                                                      COALESCE((SELECT array_agg(DISTINCT x.property) FROM contracts x WHERE x.vendor = ce.vendor AND x.property IS NOT NULL AND x.status <> 'draft'), '{}') AS properties
                                               FROM certificates ce LEFT JOIN contracts c ON c.id = ce.contract_id""")).mappings()]
    order = {"expired": 0, "expiring": 1, "missing": 2, "valid": 3}
    for r in rows:
        r["status"] = status(r["expiry_date"], today)
        r["days_left"] = (r["expiry_date"] - today).days if r["expiry_date"] else None
    rows.sort(key=lambda r: (order[r["status"]], r["expiry_date"] or date.max, r["vendor"]))
    return {"certificates": rows, "summary": {k: sum(1 for r in rows if r["status"] == k) for k in order}, "soon_days": SOON_DAYS}
