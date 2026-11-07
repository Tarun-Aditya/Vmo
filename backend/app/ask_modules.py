"""Offline answers for every module of the app, over the same views the pages read: obligations, SLA, invoices, spend exceptions, vendor risk, alerts, the draft review
queue, template deviations, templates and term benchmarks. A small declarative registry (view, filters, groupings, measures) is compiled into SQL, so a question
can be a list, a group-by or an aggregate, over the whole portfolio, one vendor or the documents selected in the UI. Claude answers the same questions with run_sql
over the same views (see prompts/schema.md); the module eval cross-validates both against the numbers the pages show."""
from __future__ import annotations

import re

from sqlalchemy import text

from app.ask_nl import _run, money
from app.db import SessionLocal

SEVS = r"(critical|high|medium|low)"
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "ten": 10}


def _n(s: str) -> int:
    return int(s) if s.isdigit() else NUM.get(s, 1)


def _vendors() -> list[str]:
    with SessionLocal() as s:
        return [r[0] for r in s.execute(text("SELECT DISTINCT vendor FROM contracts WHERE vendor IS NOT NULL"))]


def _metrics() -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text("SELECT key, name, unit FROM metrics WHERE enabled")).mappings()]


def _clause_types() -> list[str]:
    with SessionLocal() as s:
        return [r[0] for r in s.execute(text("SELECT DISTINCT clause_type FROM template_clauses"))]


# (key, view, noun, keyword regexes with weights, base where, vendor column?, contract_id column?, date column for windows, dims, sum measures, list columns, list order)
MODULES: list[dict] = [
    dict(key="obligations", view="v_obligations", noun="obligation", base=["contract_status <> 'draft'"], vendor="vendor", cid="contract_id", date="due_date", future=True,
         kw=[(r"\bobligations?\b|\bduties\b|\bduty\b|\bmilestones?\b|\bdeliverables?\b|\bowed\b", 3)],
         dims={"vendor": ("vendor", r"vendor|supplier"), "kind": ("kind", r"kind|type of obligation|category"), "status": ("status", r"status"), "party": ("party", r"party|side|who"),
               "contract": ("title", r"contract|agreement|document"), "month": ("to_char(due_date, 'YYYY-MM')", r"month")},
         sums={}, cols="title, vendor, kind, party, obligation, due_date, status, days_left", order="due_date, title",
         filters=[(r"\boverdue\b|\blate\b|\bmissed\b|past due", "status = 'overdue'", "overdue"), (r"\bopen\b|outstanding|\bpending\b|not (?:yet )?(?:done|delivered|completed)", "status = 'open'", "open"),
                  (r"\bdone\b|\bcompleted\b|\bdelivered\b|\bfulfilled\b", "status = 'done'", "done"), (r"\bsupplier obligations\b|owed by (?:the )?(?:supplier|vendor)|(?:supplier|vendor)s? (?:must|owes?|is responsible|are responsible)|obligations? (?:does|do) the (?:supplier|vendor)", "party = 'Supplier'", "owed by the supplier"),
                  (r"\bcustomer obligations\b|owed by (?:the )?customer|we (?:must|owe)|(?:customer|arcadia) (?:must|owes?)", "party = 'Customer'", "owed by us"), (r"\bmilestones?\b", "kind = 'milestone'", "milestones"),
                  (r"\bsla obligations?\b|service level obligations?", "kind = 'sla'", "SLA"), (r"\brenewal notice|notice obligations?\b", "kind IN ('notice','renewal')", "notices"),
                  (r"\bpayment obligations?\b", "kind = 'payment'", "payment")]),
    dict(key="sla", view="v_sla_credit", noun="SLA measurement", base=[], vendor="vendor", cid="contract_id", date="period", future=False,
         kw=[(r"\bsla\b|service[- ]levels?|\bavailability\b|\buptime\b|\bbreach(?:es|ed)?\b(?! of)|missed (?:their |the )?(?:target|sla)|\bshortfall\b", 3), (r"service credits?|\bcredits?\b", 5)],
         dims={"vendor": ("vendor", r"vendor|supplier"), "contract": ("title", r"contract|agreement|document"), "metric": ("metric_key", r"metric|service level|measure"),
               "month": ("to_char(period, 'YYYY-MM')", r"month")},
         sums={"shortfall": ("SUM(shortfall)", "total shortfall", r"shortfall"), "credit": ("ROUND(SUM(credit_usd))", "estimated service credits", r"credit")}, cols="vendor, title, metric_key, period, actual, target, shortfall, incidents", order="period DESC, vendor",
         filters=[(r"\bbreach(?:es|ed)?\b|missed|below (?:the )?target|failed|\bmiss\b", "breach", "breached")]),
    dict(key="exceptions", view="v_spend_exceptions", noun="spend exception", base=[], vendor="vendor", cid="contract_id", date="invoice_date", future=False,
         kw=[(r"exceptions?|anomal\w+|duplicate\w*|over[- ]?bill\w*|over (?:the )?contract value|run[- ]rate|billed (?:before|after)|unsigned contract|off[- ]contract|no contract on file", 4)],
         dims={"kind": ("kind", r"kind|type|reason"), "severity": ("severity", r"severity"), "vendor": ("vendor", r"vendor|supplier"), "contract": ("contract_title", r"contract|agreement")},
         sums={"at_risk": ("SUM(amount_at_risk)", "amount at risk", r"at risk|exposure|amount|total|how much")}, cols="severity, kind, vendor, contract_title, invoice_no, invoice_amount, amount_at_risk, detail",
         order="CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, amount_at_risk DESC",
         filters=[(r"duplicate", "kind = 'duplicate'", "duplicates"), (r"no contract|off[- ]contract|without (?:a )?contract|not on file", "kind = 'no_contract'", "no contract on file"),
                  (r"unsigned", "kind = 'unsigned_contract'", "unsigned contract"), (r"run[- ]rate", "kind = 'above_run_rate'", "above run rate"),
                  (r"over (?:the )?contract value|over[- ]?billed|above (?:the )?contract value", "kind = 'over_contract_value'", "over contract value"),
                  (r"billed before|before (?:the )?(?:effective|start)", "kind = 'billed_before_effective'", "billed before effective"), (r"billed after|after (?:the )?expiry", "kind = 'billed_after_expiry'", "billed after expiry"),
                  (r"late payment", "kind = 'late_payment'", "late payment"), (rf"\b{SEVS}[- ]severity\b|\b{SEVS}\s+(?:spend\s+)?exceptions?\b|serious", None, None)]),
    dict(key="invoices", view="v_invoices", noun="invoice", base=[], vendor="vendor", cid="contract_id", date="invoice_date", future=False,
         kw=[(r"invoices?|invoiced|\bbilled\b|billing|\bspend\b|\bspent\b|\bpaid\b|\bunpaid\b|payments? (?:to|made)", 2)],
         dims={"vendor": ("vendor", r"vendor|supplier"), "contract": ("contract_title", r"contract|agreement"), "month": ("to_char(invoice_date, 'YYYY-MM')", r"month"), "year": ("to_char(invoice_date, 'YYYY')", r"year")},
         sums={"amount": ("SUM(amount)", "total invoiced", r"total|how much|sum|amount|spend|spent|invoiced|billed|worth"), "avg_amount": ("ROUND(AVG(amount), 2)", "average invoice", r"average|mean|avg")}, cols="vendor, contract_title, invoice_no, invoice_date, due_date, paid_date, amount, days_paid_late",
         order="invoice_date DESC, vendor",
         filters=[(r"no contract|without (?:a )?contract|off[- ]contract|no matching contract|not on file", "contract_id IS NULL", "with no contract on file"),
                  (r"paid late|late(?:ly)? paid|late payments?|paid after (?:the )?due|after (?:the )?due date|overdue payments?", "days_paid_late > 0", "paid late"), (r"unpaid|outstanding|not (?:yet )?paid", "paid_date IS NULL", "unpaid")]),
    dict(key="risk", view="v_vendor_scores", noun="vendor", base=[], vendor="vendor", cid=None, date=None, future=False,
         kw=[(r"risk(?:s|y|iest)?\b|risk scores?|\btiers?\b|scorecards?", 3)],
         dims={"tier": ("tier", r"tier|level|rating")}, sums={"score": ("ROUND(AVG(score)::numeric, 1)", "average risk score", r"average|mean|avg")},
         cols="vendor, score, tier, contract_risk, renewal_exposure, performance, spend_compliance, concentration", order="score DESC",
         filters=[(rf"\b{SEVS}[- ]risk\b|\b{SEVS} tier\b|tier {SEVS}", None, None), (r"score (?:above|over|greater than|>)\s*(\d+)", "score > {0}", "score above {0}"), (r"score (?:below|under|less than|<)\s*(\d+)", "score < {0}", "score below {0}")]),
    dict(key="alerts", view="v_alerts", noun="alert", base=[], vendor="vendor", cid="contract_id", date="created_at", future=False,
         kw=[(r"\balerts?\b|notifications?", 4)],
         dims={"severity": ("severity", r"severity"), "status": ("status", r"status"), "rule": ("rule_key", r"rule|type|kind"), "vendor": ("vendor", r"vendor|supplier")},
         sums={}, cols="severity, title, vendor, status, rule_key, created_at", order="CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC",
         filters=[(r"resolved|closed", "status = 'resolved'", "resolved"), (r"acknowledged", "status = 'acknowledged'", "acknowledged"), (rf"\b{SEVS}\b(?= (?:severity )?alerts?)|{SEVS}[- ]severity", None, None)]),
    dict(key="reviews", view="v_reviews", noun="draft", base=[], vendor="vendor", cid="contract_id", date="due_date", future=True,
         kw=[(r"review queue|awaiting review|waiting for review|(?:drafts?|redlines?) .{0,30}review|assign(?:ed|ee)|reviewer|to review|approved drafts?|pending review", 4)],
         dims={"status": ("review_status", r"status|state"), "assignee": ("COALESCE(assignee, 'unassigned')", r"assignee|reviewer|owner|person"), "vendor": ("vendor", r"vendor|supplier"), "type": ("type", r"type")},
         sums={"deviations": ("SUM(deviations)", "total changes", r"deviations|changes|redline"), "checks": ("SUM(checks_failed)", "checklist failures", r"checklist|checks|failures")},
         cols="title, vendor, review_status, assignee, due_date, deviations, checks_failed, days_waiting", order="days_waiting DESC NULLS LAST, title",
         filters=[(r"unassigned|no assignee|not assigned", "assignee IS NULL", "unassigned"), (r"overdue review|review is overdue|past (?:the )?due", "due_date < CURRENT_DATE AND review_status <> 'approved'", "review overdue"),
                  (r"\bpending\b|\bto review\b|waiting for review|awaiting review", "review_status = 'pending'", "waiting for review"), (r"in review|being reviewed", "review_status = 'in_review'", "in review"),
                  (r"changes requested", "review_status = 'changes_requested'", "changes requested"), (r"\bapproved\b", "review_status = 'approved'", "approved")]),
    dict(key="deviations", view="v_deviations", noun="deviation", base=[], vendor="vendor", cid="contract_id", date=None, future=False,
         kw=[(r"deviat\w+|depart\w* from (?:the )?(?:standard|template)|differ\w* from (?:the )?(?:standard|template)|non[- ]standard", 4)],
         dims={"severity": ("severity", r"severity"), "clause": ("clause_type", r"clause"), "template": ("template", r"template"), "vendor": ("vendor", r"vendor|supplier"), "contract": ("title", r"contract|document|draft")},
         sums={}, cols="title, vendor, template, clause_type, severity, deviation_summary", order="CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, title",
         filters=[(r"\bdrafts?\b", "status = 'draft'", "in vendor drafts"), (r"executed|signed|active", "status <> 'draft'", "in executed contracts"), (rf"\b{SEVS}\b(?= (?:severity )?deviations?)|{SEVS}[- ]severity", None, None)]),
    dict(key="templates", view="template_clauses tc JOIN templates t ON t.id = tc.template_id", noun="template clause", base=[], vendor=None, cid=None, date=None, future=False,
         kw=[(r"templates?|playbook|standard clauses?", 3)],
         dims={"template": ("t.name", r"template"), "clause": ("tc.clause_type", r"clause"), "severity": ("tc.severity_if_missing", r"severity")},
         sums={"templates": ("COUNT(DISTINCT t.name)", "templates", r"template")},
         cols="t.name AS template, tc.clause_type, tc.severity_if_missing, tc.playbook_position", order="t.name, tc.clause_type",
         filters=[(rf"\b{SEVS}\b(?= (?:severity )?clauses?)", None, None), (r"\b(msa|sow|nda|saas|dpa)\b", "t.type ILIKE '{0}'", "{0} template"), (r"work order", "t.type = 'Work Order'", "work order template")]),
    dict(key="benchmarks", view="v_values", noun="value", base=["status <> 'draft'"], vendor="vendor", cid="contract_id", date=None, future=False,
         kw=[(r"median|benchmark|typical|portfolio average|average (?!annual)|lowest|highest|shortest|longest|minimum|maximum", 2)],
         dims={"vendor": ("vendor", r"vendor|supplier"), "type": ("type", r"type")}, sums={}, cols="title, vendor, metric, value_num, unit", order="value_num", filters=[]),
]


def _pick(q: str) -> dict | None:
    best, score = None, 0
    for m in MODULES:
        sc = sum(w * len(re.findall(rx, q)) for rx, w in m["kw"])
        if m["key"] == "benchmarks":                      # only when a configured term is named as well
            sc = sc if _metric_hits(q) else 0
        if sc > score:
            best, score = m, sc
    return best


def _metric_hits(q: str) -> list[dict]:
    out = []
    for m in _metrics():
        words = [w[:5] for w in re.findall(r"[a-z]{4,}", m["name"].lower())]
        if words and all(w in q for w in words if w not in ("limit", "period", "days", "notice")) and any(w in q for w in words):
            out.append(m)
    return out


def _window(q: str, m: dict) -> tuple[str, str] | None:
    col = m.get("date")
    if not col:
        return None
    mt = re.search(r"(?:next|within|in the next|coming)\s+(\w+)\s+(day|week|month)s?", q)
    if mt and m["future"]:
        d = _n(mt.group(1)) * {"day": 1, "week": 7, "month": 30}[mt.group(2)]
        return f"{col} BETWEEN CURRENT_DATE AND CURRENT_DATE + {d}", f"due in the next {_n(mt.group(1))} {mt.group(2)}s"
    mt = re.search(r"(?:last|past|previous)\s+(\w+)\s+(day|week|month)s?", q)
    if mt:
        n, u = _n(mt.group(1)), mt.group(2)
        start = f"date_trunc('month', CURRENT_DATE) - interval '{n - 1} month'" if u == "month" else f"CURRENT_DATE - {n * (7 if u == 'week' else 1)}"
        return f"{col} >= {start}", f"in the last {n} {u}s"
    if re.search(r"this year", q):
        return f"{col} >= date_trunc('year', CURRENT_DATE)", "this year"
    if re.search(r"this month", q):
        return f"{col} >= date_trunc('month', CURRENT_DATE)", "this month"
    return None


def parse(question: str, scope: list[int] | None = None) -> dict | None:
    q = question.lower().replace("’", "'")
    m = _pick(q)
    if not m:
        return None
    where, labels = list(m["base"]), []
    for rx, sql, label in m["filters"]:
        mt = re.search(rx, q)
        if not mt:
            continue
        if sql is None:                                           # severity / tier word captured by the regex
            word = next((g for g in mt.groups() if g), None)
            col = {"risk": "tier", "alerts": "severity", "deviations": "severity", "exceptions": "severity", "templates": "tc.severity_if_missing"}[m["key"]]
            if word:
                where.append(f"{col} = '{word}'")
                labels.append(word)
        else:
            where.append(sql.format(*[g for g in mt.groups()]) if "{0}" in sql else sql)
            labels.append((label or "").format(*mt.groups()) if label else "")
    if m["key"] == "alerts" and not any("status" in w for w in where) and not re.search(r"\ball alerts\b|every alert|ever raised|any status", q):
        where.append("status = 'open'")
        labels.append("open")
    if m["key"] == "obligations" and not re.search(r"\bdone\b|\bcompleted\b|\ball obligations\b", q) and not any("status" in w for w in where) and re.search(r"due|next|upcoming|coming", q):
        where.append("status IN ('open', 'overdue')")
    w = _window(q, m)
    if w:
        where.append(w[0])
        labels.append(w[1])
    if m["key"] == "obligations" and w and "future" in w[1] or (m["key"] == "obligations" and w and "next" in w[1]):
        where.append("status IN ('open', 'overdue') AND due_date >= CURRENT_DATE" if not any("status" in x for x in where) else "due_date >= CURRENT_DATE")
    if scope and m["cid"]:
        where.append(f"{m['cid']} IN ({', '.join(str(int(i)) for i in scope)})")
    elif m["vendor"]:
        qn = re.sub(r"[^a-z0-9 ]", " ", q)
        hit = [v for v in _vendors() if re.sub(r"[^a-z0-9 ]", " ", v.lower()).split()[0] in qn.split() and len(v.split()[0]) >= 4]
        hit = [v for v in hit if re.sub(r"[^a-z0-9 ]", " ", v.lower()).split()[0] in qn.split()]
        if hit:
            where.append("vendor IN (" + ", ".join("'" + v.replace("'", "''") + "'" for v in hit) + ")")
            labels.append(f"for {hit[0]}")
    mets = _metric_hits(q) if m["key"] == "benchmarks" else []
    if mets:
        where.append("metric_key = '" + mets[0]["key"] + "'")
    group = None
    for g in re.finditer(r"\b(?:by|per|each|for every|split by|grouped by|group by|broken down by|across|of each)\s+(?:the\s+)?(\w+)(?:\s+(\w+))?", q):
        for word in g.groups():
            for name, (_, rx) in m["dims"].items():
                if word and re.fullmatch(rf"(?:{rx})s?(?:es)?", word):
                    group = group or name
    topn = re.search(r"\btop\s+(\w+)|\b(\w+)\s+(?:highest|largest|biggest|riskiest|worst|most)\b|\bhighest\s+(\w+)\b", q)
    top = None
    if topn:
        v = next((x for x in topn.groups() if x), "")
        top = _n(v) if (v.isdigit() or v in NUM) else None
    superlative = bool(re.search(r"\b(highest|largest|biggest|riskiest|worst|most|lowest|smallest|least)\b", q)) and not top
    if superlative:
        top = 1
    if m["key"] == "risk" and re.search(r"how many|number of|count", q):
        top = None
    measure = "count"
    if re.search(r"\bmedian\b", q):
        measure = "median"
    elif re.search(r"average|\bavg\b|\bmean\b", q):
        measure = "avg" if m["key"] == "benchmarks" else next((k for k, (_, _, rx) in m["sums"].items() if re.search(r"average|mean|avg", rx)), "count")
    elif re.search(r"\bminimum\b|\bshortest\b|\blowest\b|\bsmallest\b", q) and m["key"] == "benchmarks":
        measure = "min"
    elif re.search(r"\bmaximum\b|\blongest\b|\bhighest\b|\blargest\b", q) and m["key"] == "benchmarks":
        measure = "max"
    else:
        for name, (_, _, rx) in m["sums"].items():
            if re.search(rx, q) and not re.search(r"how many|number of|\bcount\b", q) and re.search(r"total|how much|sum|worth|\bamount|at risk|spend|spent|invoiced|billed|by (?:vendor|kind|type|severity)|per ", q):
                measure = name
                break
    if m["key"] == "templates" and re.search(r"how many (?:standard )?templates|number of (?:standard )?templates|templates do we have|count (?:of )?(?:standard )?templates", q):
        measure = "templates"
    if m["key"] == "invoices" and measure == "count" and re.search(r"how much|total|spend|spent", q):
        measure = "amount"
    if m["key"] == "exceptions" and measure == "count" and re.search(r"how much|total amount|at risk", q):
        measure = "at_risk"
    return dict(m=m, where=where, labels=[x for x in labels if x], group=group, top=top, measure=measure, mets=mets, scope=scope, question=question,
                count_q=bool(re.search(r"how many|number of|\bcount\b", q)), list_q=bool(re.search(r"\blist\b|\bshow\b|which|what are|who|name", q)))


def _measure_sql(p: dict) -> tuple[str, str]:
    m, me = p["m"], p["measure"]
    if me == "count":
        return "COUNT(*)", "n"
    if me in ("median", "avg", "min", "max"):
        return {"median": "percentile_cont(0.5) WITHIN GROUP (ORDER BY value_num)", "avg": "AVG(value_num)", "min": "MIN(value_num)", "max": "MAX(value_num)"}[me], me
    sql, _, _ = m["sums"][me]
    return sql, me


def build(p: dict) -> dict[str, str]:
    m = p["m"]
    w = ("WHERE " + " AND ".join(p["where"])) if p["where"] else ""
    ms, mname = _measure_sql(p)
    base_cols = "COUNT(*) AS n" + (f", {ms} AS {mname}" if mname != "n" else "")
    out = {"aggregate": f"SELECT {base_cols} FROM {m['view']} {w}"}
    cols = m["cols"] if "AS template" in m["cols"] else m["cols"]
    lim = f" LIMIT {p['top']}" if p["top"] and not p["group"] else " LIMIT 200"
    out["list"] = f"SELECT {cols} FROM {m['view']} {w} ORDER BY {m['order']}{lim}"
    if p["group"]:
        expr = m["dims"][p["group"]][0]
        order = "2 DESC, 1" if mname == "n" else "3 DESC, 1"
        out["group"] = f"SELECT {expr} AS {p['group']}, {base_cols} FROM {m['view']} {w} GROUP BY 1 ORDER BY {order}" + (f" LIMIT {p['top']}" if p["top"] else "")
    return out


def _fmt(p: dict, v) -> str:
    if v is None:
        return "—"
    if p["measure"] in ("amount", "at_risk", "credit"):
        return money(v)
    return f"{float(v):g}" if isinstance(v, (int, float)) or hasattr(v, "quantize") else str(v)


def answer(question: str, scope: list[int] | None = None) -> dict | None:
    p = parse(question, scope)
    if not p:
        return None
    m, sql, calls = p["m"], build(p), []
    plan = [{"title": "Understood the question", "detail": f"Module: {m['key']} (view {m['view'].split()[0]}) · measure: {p['measure']}" + (f" · grouped by {p['group']}" if p["group"] else "")
             + " · filters: " + (", ".join(p["labels"]) or "none") + " · scope: " + (f"{len(scope)} selected document(s)" if scope else "whole portfolio")}]
    agg = _run(sql["aggregate"], calls, "Headline numbers")[0]
    calls[-1]["no_tiles"] = True
    n = agg["n"]
    noun = m["noun"] + ("" if n == 1 else "s")
    flt = (" (" + ", ".join(p["labels"]) + ")") if p["labels"] else ""
    if n == 0:
        return {"answer": f"No {m['noun']}s match{flt}.", "tool_calls": calls, "plan_steps": plan}
    head = f"{n} {noun}{flt}"
    if p["measure"] != "count":
        key = next(k for k in agg if k not in ("n",))
        head += f"; {('median' if p['measure'] == 'median' else m['sums'][p['measure']][1] if p['measure'] in m['sums'] else p['measure'])}: {_fmt(p, agg[key])}"
    head += "."
    if p["group"]:
        rows = _run(sql["group"], calls, f"By {p['group']}", True)
        mk = next((k for k in rows[0] if k not in (p["group"], "n")), "n") if rows else "n"
        head += f" By {p['group']}: " + "; ".join(f"{r[p['group']]} {_fmt(p, r[mk]) if mk != 'n' else r['n']}" for r in rows[:6]) + ("…" if len(rows) > 6 else "") + "."
    else:
        rows = _run(sql["list"], calls, m["noun"].capitalize() + "s", True)
        if p["top"] and rows:
            head += f" Top {len(rows)} shown."
    return {"answer": head, "tool_calls": calls, "plan_steps": plan}
