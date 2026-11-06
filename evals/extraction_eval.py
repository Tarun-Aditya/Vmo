"""Per-field extraction accuracy vs data/labels.json (dates exact, money +-1%, booleans exact)."""

import json
import sys
from collections import defaultdict

from app.config import data_path
from app.db import SessionLocal
from app.docgen.generate import KEY_FIELDS
from sqlalchemy import text

MONEY = {"annual_value", "total_value"}
THRESHOLD = 0.90


def same(field, got, want):
    if want is None or got is None:
        return want is None and got is None
    if field in MONEY:
        return abs(float(got) - float(want)) <= 0.01 * abs(float(want))
    if field in ("liability_cap_multiple",):
        return abs(float(got) - float(want)) < 1e-6
    if field.endswith("_date"):
        return str(got) == str(want)
    return got == want


def main() -> int:
    labels = json.loads((data_path() / "labels.json").read_text())["contracts"]
    manifest = json.loads((data_path() / "manifest.json").read_text())["contracts"]
    key_by_title = {m["title"]: m["key"] for m in manifest}
    ok, tot, per_field, misses = 0, 0, defaultdict(lambda: [0, 0]), []
    with SessionLocal() as s:
        rows = s.execute(text("SELECT * FROM contracts")).mappings().all()
    for r in rows:
        want = labels[key_by_title[r["title"]]]
        for f in KEY_FIELDS:
            if f not in want:  # amendments only label the terms they change
                continue
            good = same(f, r[f], want[f])
            per_field[f][0] += good
            per_field[f][1] += 1
            ok += good
            tot += 1
            if not good:
                misses.append((r["title"], f, r[f], want[f]))
    print("Extraction accuracy by field:")
    for f, (g, n) in per_field.items():
        print(f"  {f:30s} {g}/{n}  {g / n:6.1%}")
    for m in misses[:15]:
        print("  MISS", m)
    acc = ok / tot
    print(f"OVERALL {ok}/{tot} = {acc:.1%} (threshold {THRESHOLD:.0%})")
    return 0 if acc >= THRESHOLD else 1


if __name__ == "__main__":
    sys.exit(main())
