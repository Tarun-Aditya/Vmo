"""Redline eval on the hotel corpus: recall of the planted deviations per draft, and noise (findings that were not planted), plus the clean control draft.
Needs the hotel corpus loaded (python -m app.seed --hotel) and the API's DB env. Offline engine: LLM_PROVIDER=offline."""
import json
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import data_path  # noqa: E402
from app.db import SessionLocal  # noqa: E402

CLAUSE = {"payment_terms": {"payment"}, "liability_cap": {"liability_cap"}, "termination_for_convenience": {"termination_for_convenience"}, "renewal": {"renewal"}, "governing_law": {"governing_law"},
          "insurance": {"insurance"}, "warranties": {"warranties"}, "sla": {"sla"}, "data_protection": {"data_protection", "security", "breach_notification"}, "ip_ownership": {"ip_ownership"}}


def main() -> int:
    lab = json.loads((data_path() / "labels_hotel.json").read_text())
    tot_hit = tot_plant = tot_found = 0
    clean_bad = 0
    with SessionLocal() as s:
        for key, d in lab["drafts"].items():
            m = d["meta"]
            row = s.execute(text("SELECT c.id, r.items FROM contracts c JOIN redlines r ON r.contract_id=c.id WHERE c.vendor ILIKE :v AND c.status='draft'"), {"v": f"%{m['vendor'].split()[0]}%"}).first()
            if not row:
                print(f"{key}: not found")
                continue
            items = row[1] or []
            got = {i["clause_type"]: i["severity"] for i in items}
            plant = d.get("deviations", [])
            hit = [p for p in plant if CLAUSE.get(p, {p}) & set(got)]
            extra = [k for k in got if not any(k in CLAUSE.get(p, {p}) for p in plant)]
            tot_hit += len(hit)
            tot_plant += len(plant)
            tot_found += len(items)
            hi = [k for k, v in got.items() if v in ("high", "critical")]
            if not plant:
                clean_bad += len(hi)
            print(f"{key:26} planted {len(plant)} found {len(hit)}/{len(plant)}  total findings {len(items):2}  not-planted {len(extra):2}  high/critical {len(hi)}  missed {sorted(set(plant) - set(hit))}")
    print(f"RECALL {tot_hit}/{tot_plant}  findings per draft {tot_found / max(len(lab['drafts']), 1):.1f}  control high/critical: {clean_bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
