"""Ask over every module, cross-validated against what each page shows.
Each question's expected answer is computed from the module's own API (the numbers on that page), never from the SQL Ask writes. Cases cover aggregates, group-bys and lists,
over the whole portfolio and over one selected document. Run with LLM_PROVIDER=offline (module engine) or unset (Claude), optionally `--only <prefix>`.
Usage: python evals/module_eval.py [--only obl] [--json out.json]"""
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from app import ask, llm
from app.main import app

C = TestClient(app)
G = lambda p: C.get(p).json()  # noqa: E731


def tables(res):
    out = []
    for c in res.get("tool_calls", []):
        o = c.get("output") or {}
        if c["name"] == "run_sql" and o.get("rows") is not None:
            out.append((o["columns"], o["rows"]))
    return out


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) or hasattr(x, "quantize")


def check(kind, want, res):
    ts = tables(res)
    if kind == "number":
        w = float(want)
        cells = [float(v) for cols, rows in ts if len(rows) <= 3 for r in rows for v in r if num(v)]
        return any(abs(v - w) <= max(0.006 * abs(w), 0.06) for v in cells), f"want {w:g}; numbers {sorted(set(round(c, 2) for c in cells))[:8]}"
    if kind == "set":
        for cols, rows in ts:
            for i in range(len(cols)):
                if {str(r[i]) for r in rows if r[i] is not None} == set(want):
                    return True, ""
        best = max(({str(r[i]) for r in rows if r[i] is not None} for cols, rows in ts for i in range(len(cols))), key=lambda s: len(s & set(want)), default=set())
        return False, f"want {sorted(want)[:8]}({len(want)}); closest {sorted(best)[:8]}({len(best)})"
    if kind == "dict":
        want = {str(k): float(v) for k, v in want.items() if v}
        seen = []
        for cols, rows in ts:
            for ki in range(len(cols)):
                for vi in range(len(cols)):
                    if ki == vi:
                        continue
                    try:
                        got = {str(r[ki]): float(r[vi]) for r in rows if r[vi] is not None and float(r[vi]) != 0}
                    except (TypeError, ValueError):
                        continue
                    seen.append(got)
                    if got.keys() == want.keys() and all(abs(got[k] - want[k]) <= max(0.006 * abs(want[k]), 0.06) for k in want):
                        return True, ""
        return False, f"want {dict(list(want.items())[:6])}; closest {max(seen, key=lambda g: len(g.keys() & want.keys()), default={})}"
    return False, "unknown kind"


def cases():
    meta = G("/api/meta")
    obl = G("/api/obligations")["rows"]
    sla = G("/api/sla")
    sp, ex, inv = G("/api/spend/summary"), G("/api/spend/exceptions"), G("/api/invoices")
    risk = G("/api/risk/vendors")["vendors"]
    bm = {m["metric_key"]: m for m in G("/api/benchmarks")["metrics"]}
    docs = G("/api/redline/documents")
    drafts = [d for d in docs if d["status"] == "draft"]
    alerts = G("/api/alerts?status=all&limit=500")["items"]
    tpl = G("/api/templates")
    dash = G("/api/dashboard")["kpis"]
    vend = G("/api/vendors")
    cons = [c for c in G("/api/contracts") if c["status"] != "draft"]
    matrix = next(g for g in G("/api/clause-matrix")["groups"] if g["name"].startswith("Executed"))["rows"]
    cnt = lambda it, f=lambda x: True, k=lambda x: x: dict(Counter(k(x) for x in it if f(x)))  # noqa: E731
    open_al = [a for a in alerts if a["status"] == "open"]
    by_con = defaultdict(list)
    for o in obl:
        by_con[o["contract_id"]].append(o)
    obl_doc = max(by_con, key=lambda k: len(by_con[k]))
    sla_doc = next((s for s in sla["series"] if s["breaches"] > 0), None)
    inv_doc = max({i["contract_id"] for i in inv if i["contract_id"]}, key=lambda c_: sum(1 for i in inv if i["contract_id"] == c_))
    L = []
    add = lambda cid, q, kind, want, scope=None: L.append((cid, q, kind, want, scope))  # noqa: E731
    # -- dashboard / repository / vendors / key clauses
    add("dash.expiring_90", "How many contracts are expiring in the next 90 days?", "number", dash["expiring_90"])
    add("dash.uncapped", "How many contracts have uncapped liability?", "number", dash["uncapped"])
    add("dash.annual_value", "What is the total annual value of all active contracts?", "number", dash["annual_value"])
    add("repo.by_type", "How many contracts do we have of each type?", "dict", cnt(cons, lambda c_: c_["type"] != "Amendment", lambda c_: c_["type"]))       # amendments are folded into the agreement they amend, as on the dashboard
    add("vend.count", "How many vendors do we have?", "number", len(vend))
    add("vend.no_tfc", "Which vendors have contracts that cannot be terminated for convenience?", "set", {v["vendor"] for v in vend if v["no_tfc"]})
    add("clauses.indemnity", "How many contracts have an indemnity clause?", "number", sum(1 for r in matrix if r["cells"].get("indemnity", {}).get("present")))
    # -- obligations
    add("obl.overdue", "How many obligations are overdue?", "number", sum(o["status"] == "overdue" for o in obl))
    add("obl.open", "How many open obligations are there?", "number", sum(o["status"] == "open" for o in obl))
    add("obl.overdue_by_vendor", "How many overdue obligations does each vendor have?", "dict", cnt(obl, lambda o: o["status"] == "overdue", lambda o: o["vendor"]))
    add("obl.by_kind", "Count obligations by kind", "dict", cnt(obl, k=lambda o: o["kind"]))
    add("obl.milestones_overdue", "How many milestone obligations are overdue?", "number", sum(o["status"] == "overdue" and o["kind"] == "milestone" for o in obl))
    add("obl.due_30", "How many obligations are due in the next 30 days?", "number", G("/api/obligations")["summary"]["due_30"])
    add("obl.supplier", "How many obligations does the supplier owe?", "number", sum(o["party"] == "Supplier" for o in obl))
    add("obl.doc_list", "List the obligations", "set", {o["obligation"] for o in by_con[obl_doc]}, [obl_doc])
    # -- SLA
    add("sla.breaches", "How many SLA breaches have there been in total?", "number", sla["summary"]["breach_months"])
    sb = defaultdict(int)
    for s in sla["series"]:
        sb[s["vendor"]] += s["breaches"]
    add("sla.by_vendor", "How many SLA breaches does each vendor have?", "dict", dict(sb))
    add("sla.vendors", "Which vendors missed their SLA?", "set", {v for v, n in sb.items() if n})
    if sla_doc:
        add("sla.doc", "How many SLA breaches does this contract have?", "number", sla_doc["breaches"], [sla_doc["contract_id"]])
    add("sla.credits", "What is the total estimated service credit owed?", "number", sla["summary"]["credit_usd"])
    cv = defaultdict(float)
    for s_ in sla["series"]:
        cv[s_["vendor"]] += s_["credit_usd"]
    add("sla.credits_by_vendor", "Estimated service credits by vendor", "dict", dict(cv))
    # -- spend
    add("spend.billed", "What is the total invoiced amount?", "number", sp["billed"])
    add("spend.off_contract", "How much was invoiced by vendors with no contract on file?", "number", sp["off_contract"])
    byv = defaultdict(float)
    for i in inv:
        byv[i["vendor"]] += float(i["amount"])
    add("spend.by_vendor", "Total invoiced by vendor", "dict", dict(byv))
    add("spend.exceptions", "How many spend exceptions are there?", "number", sp["exceptions"])
    add("spend.by_kind", "How many spend exceptions of each kind?", "dict", cnt(ex, k=lambda e: e["kind"]))
    add("spend.paid_late", "How many invoices were paid late?", "number", sum(1 for i in inv if (i["days_paid_late"] or 0) > 0))
    add("spend.duplicates", "Which vendors sent duplicate invoices?", "set", {e["vendor"] for e in ex if e["kind"] == "duplicate"})
    add("spend.critical_at_risk", "What is the amount at risk from critical spend exceptions?", "number", sum(e["amount_at_risk"] for e in ex if e["severity"] == "critical"))
    add("spend.unpaid", "How many invoices are unpaid?", "number", sum(1 for i in inv if not i["paid_date"]))
    add("spend.doc_total", "What is the total invoiced?", "number", sum(float(i["amount"]) for i in inv if i["contract_id"] == inv_doc), [inv_doc])
    # -- risk
    add("risk.critical", "Which vendors are critical risk?", "set", {v["vendor"] for v in risk if v["tier"] == "critical"})
    add("risk.by_tier", "How many vendors are in each risk tier?", "dict", cnt(risk, k=lambda v: v["tier"]))
    add("risk.top3", "Who are the top 3 riskiest vendors?", "set", {v["vendor"] for v in sorted(risk, key=lambda v: -v["score"])[:3]})
    add("risk.avg", "What is the average vendor risk score?", "number", sum(v["score"] for v in risk) / len(risk))
    # -- benchmarks
    for key, q, f in (("payment_terms_days", "What is the median payment terms across contracts?", "median"), ("warranty_days", "What is the longest warranty period?", "max"),
                      ("confidentiality_years", "What is the average confidentiality survival in years?", None)):
        if key in bm:
            want = bm[key][f] if f else sum(v["value"] for v in bm[key]["values"]) / len(bm[key]["values"])
            add(f"bench.{key}", q, "number", want)
    # -- review queue / redline
    add("review.waiting", "How many vendor drafts are waiting for review?", "number", sum(1 for d in drafts if d["review_status"] == "pending"))
    dv = Counter()
    for d in drafts:
        for s, n in (d["counts"] or {}).items():
            dv[s] += n
    add("review.dev_by_sev", "How many deviations from the standard are there in drafts, by severity?", "dict", dict(dv))
    add("review.checks", "How many checklist failures are there across vendor drafts?", "number", sum(d["checks_failed"] for d in drafts))
    # -- alerts
    add("alerts.open", "How many open alerts are there?", "number", len(open_al))
    add("alerts.by_sev", "How many open alerts by severity?", "dict", cnt(open_al, k=lambda a: a["severity"]))
    add("alerts.critical_vendors", "Which vendors have critical alerts?", "set", {a["vendor"] for a in open_al if a["severity"] == "critical" and a["vendor"]})
    # -- templates
    add("tpl.count", "How many templates do we have?", "number", len(tpl))
    msa = next((t for t in tpl if t["type"] == "MSA"), None)
    if msa:
        add("tpl.msa_clauses", "How many clauses does the MSA template have?", "number", msa["clause_count"])
    add("tpl.deviating", "Which templates do executed contracts deviate from?", "set", {t["name"] for t in tpl if t["deviating_contracts"]})
    # -- paraphrases: same expected values, different wording (the engines must not depend on one phrasing)
    add("obl.overdue_p", "How many duties are past due?", "number", sum(o["status"] == "overdue" for o in obl))
    add("obl.by_vendor_p", "Show overdue obligations grouped by vendor", "dict", cnt(obl, lambda o: o["status"] == "overdue", lambda o: o["vendor"]))
    add("obl.by_party_p", "Split all obligations by party", "dict", cnt(obl, k=lambda o: o["party"]))
    add("sla.vendors_p", "Which suppliers have breached their service levels?", "set", {v for v, n in sb.items() if n})
    add("spend.off_contract_p", "What is the total spend with vendors that have no contract?", "number", sp["off_contract"])
    add("spend.by_sev_p", "Give me a breakdown of spend exceptions by severity", "dict", cnt(ex, k=lambda e: e["severity"]))
    add("spend.at_risk_p", "What is the total amount at risk across all spend exceptions?", "number", sp["at_risk"])
    add("spend.late_p", "Count the invoices we paid after the due date", "number", sum(1 for i in inv if (i["days_paid_late"] or 0) > 0))
    add("spend.by_month_p", "How much did we spend each month?", "dict", {k: v for k, v in cnt([{**i, "m": i["invoice_date"][:7]} for i in inv], k=lambda i: i["m"]).items()} and
        {m_: sum(float(i["amount"]) for i in inv if i["invoice_date"][:7] == m_) for m_ in {i["invoice_date"][:7] for i in inv}})
    add("risk.high_p", "List the high risk vendors", "set", {v["vendor"] for v in risk if v["tier"] == "high"})
    add("risk.top1_p", "Which vendor has the highest risk score?", "set", {max(risk, key=lambda v: v["score"])["vendor"]})
    add("alerts.crit_p", "Show critical alerts", "number", sum(1 for a in open_al if a["severity"] == "critical"))
    add("review.deviations_p", "What are the deviation counts in vendor drafts per severity?", "dict", dict(dv))
    add("tpl.count_p", "Number of standard templates", "number", len(tpl))
    add("vend.risk_count_p", "How many vendors are there in each risk tier?", "dict", cnt(risk, k=lambda v: v["tier"]))
    return L


def run_one(case):
    cid, q, kind, want, scope = case
    try:
        res = ask.answer(q, demo_mode=False, scope=scope)
        ok, why = check(kind, want, res)
        return cid, q, ok, why, res.get("source", "?")
    except Exception as e:
        return cid, q, False, f"{type(e).__name__}: {str(e)[:160]}", "error"


def main() -> int:
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else ""
    cs = [c for c in cases() if c[0].startswith(only)]
    with ThreadPoolExecutor(3 if llm.available() else 1) as ex:
        out = list(ex.map(run_one, cs))
    by = defaultdict(lambda: [0, 0])
    for cid, q, ok, why, src in out:
        by[cid.split(".")[0]][1] += 1
        by[cid.split(".")[0]][0] += ok
        print(f"{'PASS' if ok else 'FAIL'} [{src:18s}] {cid:24s} {'' if ok else q + ' -> ' + why}")
    for k, (a, b) in by.items():
        print(f"  {k:10s} {a}/{b}")
    ok = sum(o[2] for o in out)
    print(f"OVERALL {ok}/{len(out)} = {100 * ok / len(out):.1f}%")
    if "--json" in sys.argv:
        json.dump([dict(id=o[0], q=o[1], ok=o[2], why=o[3], source=o[4]) for o in out], open(sys.argv[sys.argv.index("--json") + 1], "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
