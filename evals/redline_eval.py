"""Recall of planted deviations per draft (clause-level), plus clean-control check."""

import json
import sys

from app.config import data_path
from app.db import SessionLocal
from sqlalchemy import text

SEV = ["low", "medium", "high", "critical"]


def main() -> int:
    labels = json.loads((data_path() / "labels.json").read_text())["drafts"]
    manifest = json.loads((data_path() / "manifest.json").read_text())["drafts"]
    key_by_title = {m["title"]: m["key"] for m in manifest}
    fail = False
    with SessionLocal() as s:
        rows = s.execute(
            text(
                "SELECT c.title, r.items FROM contracts c JOIN redlines r ON r.contract_id = c.id "
                "WHERE c.status = 'draft'"
            )
        ).all()
    tot_hit = tot = sev_ok = 0
    for title, items in rows:
        planted = labels[key_by_title[title]]["deviations"]
        found = {i["clause_type"]: i for i in items}
        hit = [p for p in planted if p["clause_type"] in found]
        sev = [p for p in hit if found[p["clause_type"]]["severity"] == p["severity"]]
        extra = [c for c in found if c not in {p["clause_type"] for p in planted}]
        tot_hit += len(hit)
        tot += len(planted)
        sev_ok += len(sev)
        line = (
            f"{title[:55]:55s} recall {len(hit)}/{len(planted)}  severity-match {len(sev)}/"
            f"{len(hit)}  false-positives {len(extra)}"
        )
        print(line)
        if not planted:
            bad = [i for i in items if i["severity"] in ("high", "critical")]
            print(f"   clean control: {len(items)} findings, {len(bad)} high/critical")
            fail |= bool(bad)
        fail |= len(hit) < len(planted)
    print(f"OVERALL recall {tot_hit}/{tot}; severity agreement {sev_ok}/{tot_hit}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
