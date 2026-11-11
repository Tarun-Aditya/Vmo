"""Score the pilot corpus run (python -m app.seed --pilot) against the labels computed from its spec.
Works in any engine mode: LLM_PROVIDER=offline for the rule engine, anything else for Claude. Prints accuracy per field, per document
metadata, values & limits, milestones found as obligations, and the first misses. Exit code 1 below --threshold (default 0.80)."""
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import data_path  # noqa: E402
from app.db import SessionLocal  # noqa: E402

FIELDS = ["effective_date", "expiry_date", "notice_period_days", "auto_renew", "annual_value", "total_value", "payment_terms_days", "liability_cap_multiple", "liability_cap_text",
          "termination_for_convenience", "governing_law", "processes_personal_data", "has_dpa", "customer_signatory", "supplier_signatory", "fully_executed"]


def same(field, got, want):
    if want is None:
        return got in (None, "", False) if field in ("annual_value", "total_value", "notice_period_days", "liability_cap_multiple") else got in (None, "")
    if got is None:
        return False
    if field in ("annual_value", "total_value", "liability_cap_multiple"):
        return abs(float(got) - float(want)) <= 0.01 * max(abs(float(want)), 1)
    if field in ("effective_date", "expiry_date"):
        return str(got)[:10] == str(want)[:10]
    if isinstance(want, bool):
        return bool(got) == want
    if field == "liability_cap_text":
        return str(got).split()[0].lower() == str(want).split()[0].lower()
    return str(got).strip().lower() == str(want).strip().lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=0.80)
    a = ap.parse_args()
    lab = json.loads((data_path() / os.environ.get("LABELS", "labels_pilot.json")).read_text())
    docs = {**lab["contracts"], **lab["drafts"]}
    with SessionLocal() as s:
        rows = {}
        for r in s.execute(text("SELECT c.*, p.title AS parent_title FROM contracts c LEFT JOIN contracts p ON p.id = c.parent_id")).mappings():
            stem = Path(r["source_path"] or "").stem
            rows[stem] = dict(r)
        vals = {}
        for r in s.execute(text("SELECT c.source_path, ev.metric_key, ev.value_num FROM extracted_values ev JOIN contracts c ON c.id = ev.contract_id")):
            vals.setdefault(Path(r[0]).stem, {})[r[1]] = float(r[2]) if r[2] is not None else None
        obl = {}
        for r in s.execute(text("SELECT c.source_path, o.due_date FROM obligations o JOIN contracts c ON c.id = o.contract_id WHERE o.kind='milestone'")):
            obl.setdefault(Path(r[0]).stem, set()).add(r[1].isoformat())
    tot = dict.fromkeys(["fields", "meta", "values", "milestones"], [0, 0])
    tot = {k: [0, 0] for k in tot}
    per_field: dict[str, list[int]] = {f: [0, 0] for f in FIELDS}
    misses, missing_docs = [], []
    for key, lab_ in docs.items():
        r = rows.get(key)
        if not r:
            missing_docs.append(key)
            continue
        for f in FIELDS:
            if f in ("customer_signatory", "supplier_signatory") and lab_.get("meta", {}).get("status") == "draft":
                pass
            if lab_.get("meta", {}).get("type") == "Amendment" and f not in ("effective_date", "expiry_date", "payment_terms_days"):
                continue
            if f == "payment_terms_days" and lab_["meta"]["type"] in ("NDA", "DPA"):
                continue
            if lab_.get(f) is None and f in ("termination_for_convenience", "processes_personal_data", "has_dpa", "governing_law", "payment_terms_days", "liability_cap_multiple", "liability_cap_text"):
                continue                                  # the spec says nothing about it for this document: not scored
            ok = same(f, r.get(f), lab_.get(f))
            per_field[f][0] += ok
            per_field[f][1] += 1
            tot["fields"][0] += ok
            tot["fields"][1] += 1
            if not ok:
                misses.append((key, f, r.get(f), lab_.get(f)))
        m = lab_["meta"]
        for name, got, want in (("type", r["type"], m["type"]), ("vendor", r["vendor"], m["vendor"]), ("status", r["status"], m["status"]),
                                ("parent", bool(r["parent_id"]), bool(m["parent"]))):
            ok = str(got).lower() == str(want).lower() if name != "vendor" else str(got).lower().rstrip(".") == str(want).lower()
            tot["meta"][0] += ok
            tot["meta"][1] += 1
            if not ok:
                misses.append((key, f"meta.{name}", got, want))
        for k, want in lab_["values"].items():
            got = vals.get(key, {}).get(k)
            ok = got is not None and abs(got - float(want)) <= 0.01 * max(float(want), 1)
            tot["values"][0] += ok
            tot["values"][1] += 1
            if not ok:
                misses.append((key, f"value.{k}", got, want))
        for ms in lab_["milestones"]:
            ok = ms["date"] in obl.get(key, set())
            tot["milestones"][0] += ok
            tot["milestones"][1] += 1
            if not ok:
                misses.append((key, "milestone", sorted(obl.get(key, set())), ms["date"]))
    print(f"Pilot corpus: {len(docs)} documents ({len(missing_docs)} not ingested: {missing_docs})")
    for f, (g, n) in per_field.items():
        print(f"  {f:30s} {g:3d}/{n:3d}  {g / max(n, 1):6.1%}")
    for k, (g, n) in tot.items():
        print(f"{k.upper():12s} {g}/{n} = {g / max(n, 1):.1%}")
    for m in misses[:25]:
        print("  MISS", m)
    g = sum(v[0] for v in tot.values())
    n = sum(v[1] for v in tot.values())
    print(f"OVERALL {g}/{n} = {g / max(n, 1):.1%} (threshold {a.threshold:.0%})")
    return 0 if g / max(n, 1) >= a.threshold else 1


if __name__ == "__main__":
    _ = date
    sys.exit(main())
