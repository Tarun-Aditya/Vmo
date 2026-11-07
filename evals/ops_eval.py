"""Invoices, service-level reports and acceptance certificates read from their documents, scored against data/labels_ops.json (written from the fixture rows, never from the text).
Run with LLM_PROVIDER=offline (rules only) or unset (rules + Claude gap-filling)."""
import json
import re
import sys
from collections import Counter

from app import opsdocs
from app.config import data_path

norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()  # noqa: E731


def main() -> int:
    lab = json.loads((data_path() / "labels_ops.json").read_text())
    root = data_path() / "feeds"
    ok, tot, miss, by = 0, 0, [], Counter()
    seen = Counter()

    def score(field, good, detail):
        nonlocal ok, tot
        tot += 1
        ok += bool(good)
        seen[field] += 1
        if good:
            by[field] += 1
        else:
            miss.append((field, detail))

    for fn, want in lab["invoices"].items():
        try:
            kind, rows = opsdocs.read(next(root.rglob(fn)))
            got = rows[0] if kind == "invoice" else {}
        except Exception as e:
            got = {"_err": str(e)}
        d = lambda v: str(v) if v else None  # noqa: E731
        score("invoice.recognised", "_err" not in got and got, (fn, got.get("_err")))
        for f in ("invoice_no", "invoice_date", "due_date", "paid_date"):
            score(f"invoice.{f}", d(got.get(f)) == d(want.get(f)), (fn, f, got.get(f), want.get(f)))
        score("invoice.amount", abs(float(got.get("amount") or 0) - float(want["amount"])) < 0.01, (fn, "amount", got.get("amount"), want["amount"]))
        score("invoice.vendor", norm(got.get("vendor")) == norm(want["vendor"]), (fn, "vendor", got.get("vendor"), want["vendor"]))
        if want.get("contract_title"):
            score("invoice.reference", norm(want["contract_title"]) in norm(got.get("contract_title")) or norm(got.get("contract_title")) in norm(want["contract_title"]), (fn, "ref", got.get("contract_title"), want["contract_title"]))
    for fn, want in lab["sla"].items():
        try:
            kind, rows = opsdocs.read(next(root.rglob(fn)))
        except Exception as e:
            kind, rows = None, []
            miss.append(("sla.error", (fn, str(e))))
        g = {(r["metric_key"], round(float(r["actual"]), 2), int(r["incidents"])) for r in rows}
        w = {(r["metric_key"], round(float(r["actual"]), 2), int(r["incidents"])) for r in want["rows"]}
        score("sla.rows", g == w, (fn, sorted(g), sorted(w)))
        score("sla.period", bool(rows) and str(rows[0]["period"]) == want["period"], (fn, rows and rows[0]["period"], want["period"]))
    for fn, want in lab["acceptance"].items():
        try:
            kind, rows = opsdocs.read(next(root.rglob(fn)))
            got = rows[0]
        except Exception as e:
            got = {"_err": str(e)}
        score("acceptance.completed_on", str(got.get("completed_on")) == want["completed_on"], (fn, got.get("completed_on"), want["completed_on"]))
    for f in sorted(seen):
        print(f"  {f:26s} {by[f]:3d}/{seen[f]:3d}  {100 * by[f] / seen[f]:5.1f}%")
    for m in miss[:25]:
        print("  MISS", m)
    print(f"OVERALL {ok}/{tot} = {100 * ok / tot:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
