"""REST API for the POC frontend."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import ask as ask_mod
from app import llm
from app.config import settings
from app.db import SessionLocal
from app.docgen.library import CLAUSES

router = APIRouter(prefix="/api")

SEV_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}


def q(sql: str, **params) -> list[dict[str, Any]]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), params).mappings().all()]


def q1(sql: str, **params) -> dict[str, Any] | None:
    rows = q(sql, **params)
    return rows[0] if rows else None


@router.get("/meta")
def meta():
    from app import embeddings

    row = q1("SELECT min(created_at) AS seeded_at FROM contracts")
    return {
        "llm_available": llm.available(),
        "embedding_provider": embeddings.provider(),
        "today": dt.date.today().isoformat(),
        "seeded_at": row and row["seeded_at"],
    }


# ------------------------------------------------------------------ contracts
@router.get("/contracts/filters")
def contract_filters():
    return {
        k: [
            r["v"]
            for r in q(f"SELECT DISTINCT {k} AS v FROM contracts WHERE {k} IS NOT NULL ORDER BY 1")
        ]
        for k in ("vendor", "category", "type", "owner", "status")
    }


@router.get("/contracts")
def list_contracts(
    vendor: str | None = None,
    category: str | None = None,
    type: str | None = None,
    owner: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    where, p = [], {}
    for k, v in dict(
        vendor=vendor, category=category, type=type, owner=owner, status=status
    ).items():
        if v:
            where.append(f"c.{k} = :{k}")
            p[k] = v
    if search:
        where.append("(c.title ILIKE :s OR c.vendor ILIKE :s)")
        p["s"] = f"%{search}%"
    return q(
        f"""
      SELECT c.id, c.title, c.vendor, c.category, c.type, c.owner, c.status, c.parent_id,
             c.effective_date,
             COALESCE(e.expiry_date, c.expiry_date) AS expiry_date,
             COALESCE(e.annual_value, c.annual_value) AS annual_value,
             COALESCE(e.total_value, c.total_value) AS total_value,
             c.fully_executed, c.customer_signatory, c.supplier_signatory,
             COALESCE(e.auto_renew, c.auto_renew) AS auto_renew,
             COALESCE(e.liability_uncapped, false) AS liability_uncapped,
             (SELECT count(*) FROM clause_deviations d WHERE d.contract_id = c.id) AS deviation_count
      FROM contracts c LEFT JOIN v_effective_terms e ON e.contract_id = c.id
      {"WHERE " + " AND ".join(where) if where else ""}
      ORDER BY c.vendor, CASE c.type WHEN 'MSA' THEN 0 WHEN 'SOW' THEN 1 WHEN 'Work Order' THEN 2 WHEN 'Amendment' THEN 3 ELSE 4 END, c.title""",
        **p,
    )


EFFECTIVE_FIELDS = [
    "expiry_date",
    "notice_period_days",
    "auto_renew",
    "annual_value",
    "total_value",
    "payment_terms_days",
    "liability_cap_multiple",
    "liability_cap_text",
    "termination_for_convenience",
    "governing_law",
]


TREE_ORDER = {"SOW": 0, "Work Order": 1, "Amendment": 2, "NDA": 3, "DPA": 4}


def _tree(root_id: int) -> dict:
    rows = q("SELECT id, title, type, parent_id, effective_date FROM contracts")
    kids: dict[int, list] = {}
    for r in rows:
        kids.setdefault(r["parent_id"], []).append(r)

    def build(r):
        return {
            **r,
            "children": [
                build(c)
                for c in sorted(kids.get(r["id"], []), key=lambda x: (TREE_ORDER.get(x["type"], 9), x["id"]))
            ],
        }

    return build(next(r for r in rows if r["id"] == root_id))


def _checks(cid: int) -> list[dict]:
    rows = q(
        """SELECT cr.rule_key, r.name, r.description, r.rule_type, r.suggested_text, cr.status, cr.severity,
                  cr.actual, cr.expected, cr.page, cr.excerpt
           FROM check_results cr JOIN checklist_rules r ON r.key = cr.rule_key WHERE cr.contract_id = :i""",
        i=cid,
    )
    order = {"fail": 0, "pass": 1, "na": 2}
    rows.sort(key=lambda r: (order[r["status"]], -SEV_RANK[r["severity"]], r["name"]))
    return rows


@router.get("/contracts/{cid}")
def get_contract(cid: int):
    c = q1("SELECT * FROM contracts WHERE id = :i", i=cid)
    if not c:
        raise HTTPException(404, "contract not found")
    clauses = q(
        "SELECT id, clause_type, heading, text, page FROM clauses WHERE contract_id=:i ORDER BY id",
        i=cid,
    )
    fields = q(
        """SELECT f.field, f.value, f.confidence, f.source_clause_id, f.source_page,
                         cl.heading AS source_heading
                  FROM field_extractions f LEFT JOIN clauses cl ON cl.id = f.source_clause_id
                  WHERE f.contract_id = :i ORDER BY f.id""",
        i=cid,
    )
    titles = {r["id"]: r["title"] for r in q("SELECT id, title FROM contracts")}
    eff = q1("SELECT * FROM v_effective_terms WHERE contract_id = :i", i=cid)
    effective = []
    if eff:
        for f in EFFECTIVE_FIELDS:
            src = eff[f"{f}_source"]
            effective.append(
                {
                    "field": f,
                    "value": eff[f],
                    "source_id": src,
                    "source_title": titles[src],
                    "overridden": src != cid,
                }
            )
    root = cid
    while True:
        p = q1("SELECT parent_id FROM contracts WHERE id = :i", i=root)
        if not p or not p["parent_id"]:
            break
        root = p["parent_id"]
    devs = q(
        """SELECT d.severity, d.deviation_summary, tc.clause_type, tc.id AS template_clause_id
                FROM clause_deviations d JOIN template_clauses tc ON tc.id = d.template_clause_id
                WHERE d.contract_id = :i""",
        i=cid,
    )
    for d in devs:
        d["heading"] = CLAUSES[d["clause_type"]].heading
    devs.sort(key=lambda d: -SEV_RANK[d["severity"]])
    lineage, cur = [], c
    while cur["parent_id"] and cur["type"] in ("SOW", "Work Order", "Amendment", "NDA", "DPA"):
        cur = q1("SELECT id, title, type, parent_id FROM contracts WHERE id = :i", i=cur["parent_id"])
        lineage.insert(0, {"id": cur["id"], "title": cur["title"], "type": cur["type"]})
    inherited = []
    if c["type"] in ("SOW", "Work Order") and lineage and lineage[0]["type"] == "MSA":
        m = q1("SELECT * FROM v_effective_terms WHERE contract_id = :i", i=lineage[0]["id"])
        for label, field, text_field in (
            ("Liability cap", "liability_cap_multiple", "liability_cap_text"),
            ("Governing law", "governing_law", None),
            ("Payment terms (days)", "payment_terms_days", None),
            ("Termination for convenience", "termination_for_convenience", None),
        ):
            inherited.append({"label": label, "value": m[text_field] if text_field and m[field] is None else m[field],
                              "source_id": m[f"{field}_source"], "source_title": titles.get(m[f"{field}_source"])})
    values = q(
        """SELECT ev.metric_key, m.name, m.unit, m.kind, ev.value_num, ev.value_text, ev.page, ev.confidence
           FROM extracted_values ev JOIN metrics m ON m.key = ev.metric_key WHERE ev.contract_id = :i ORDER BY m.name""",
        i=cid,
    )
    checks = _checks(cid)
    sig = {
        k: c[k]
        for k in (
            "customer_signatory", "customer_signed_date", "supplier_signatory",
            "supplier_signed_date", "fully_executed",
        )
    }
    return {
        "signatures": sig,
        "values": values,
        "checks": checks,
        "lineage": lineage,
        "inherited_terms": inherited,
        "contract": {k: v for k, v in c.items()},
        "clauses": clauses,
        "fields": fields,
        "effective_terms": effective,
        "hierarchy": _tree(root),
        "deviations": devs,
        "is_amendment": c["type"] == "Amendment",
        "overrides": c["overrides"],
        "parent": (
            {"id": c["parent_id"], "title": titles.get(c["parent_id"])} if c["parent_id"] else None
        ),
    }


# ------------------------------------------------------------------ key clauses matrix
SHORT = {
    "termination_for_convenience": "Termination for convenience",
    "termination_for_cause": "Termination for cause",
    "execution": "Signed by both parties",
}


def _cell(k: dict, clause: dict | None, doc_type: str, status: str, signed: bool) -> dict:
    expected = doc_type in (k["applies_to"] or [])
    if k["key"] == "execution":
        present = bool(signed) and status != "draft"
        if status == "draft":
            note = "Draft: not signed or executed."
        elif present:
            note = None
        elif clause:
            note = "Not fully signed. " + clause["text"]
        else:
            note = f"No signature block found in this {doc_type}."
    else:
        present = clause is not None
        note = None
        if not present:
            note = f"No {k['name']} clause found in this document. " + (
                f"The standard {doc_type} template includes one, so this is a gap."
                if expected
                else f"It is not part of the standard {doc_type} template."
            )
    return {
        "present": present,
        "expected": expected,
        "heading": k["name"],
        "page": clause["page"] if clause else None,
        "text": clause["text"][:420] if clause else None,
        "note": note,
    }


@router.get("/clause-matrix")
def clause_matrix(vendor: str | None = None):
    """Every document (rows) x key clause (columns, from the KCC library): present or absent, with a citation."""
    ks = q("SELECT key, name, applies_to FROM kcc_library WHERE enabled AND in_matrix ORDER BY sort_order, key")
    cols = [{"key": k["key"], "label": SHORT.get(k["key"], k["name"])} for k in ks]
    clause_idx = {}
    for c in q("SELECT contract_id, clause_type, heading, text, page FROM clauses ORDER BY id"):
        clause_idx.setdefault((c["contract_id"], c["clause_type"]), c)
    rows, draft_rows = [], []
    for c in q(
        """SELECT id, title, vendor, type, status, fully_executed FROM contracts
           WHERE type <> 'Amendment' AND (CAST(:vendor AS text) IS NULL OR vendor = :vendor)
           ORDER BY vendor, CASE type WHEN 'MSA' THEN 0 WHEN 'SOW' THEN 1 WHEN 'Work Order' THEN 2 ELSE 3 END, title""",
        vendor=vendor,
    ):
        cells = {k["key"]: _cell(k, clause_idx.get((c["id"], k["key"])), c["type"], c["status"], c["fully_executed"]) for k in ks}
        r = {"id": c["id"], "title": c["title"], "vendor": c["vendor"], "type": c["type"],
             "kind": "draft" if c["status"] == "draft" else "contract", "cells": cells}
        r["present_count"] = sum(1 for x in cells.values() if x["present"])
        r["gap_count"] = sum(
            1 for key, x in cells.items()
            if not x["present"] and x["expected"] and not (r["kind"] == "draft" and key == "execution")
        )
        (draft_rows if c["status"] == "draft" else rows).append(r)
    totals = {k["key"]: sum(1 for r in rows if r["cells"][k["key"]]["present"]) for k in ks}
    return {
        "columns": cols,
        "groups": [
            {"name": "Executed contracts", "rows": rows},
            {"name": "Drafts and new documents (not yet executed)", "rows": draft_rows},
        ],
        "totals": totals,
        "executed_count": len(rows),
    }


# ------------------------------------------------------------------ vendors
def _vendor_flags(v: dict) -> list[dict]:
    """Plain-language risk flags (severity encoded as in the rest of the UI), most severe first."""
    f = []
    if v["uncapped"]:
        f.append({"key": "uncapped", "severity": "critical", "label": f"{v['uncapped']} uncapped liability"})
    if v["pd_no_dpa"]:
        f.append({"key": "pd_no_dpa", "severity": "critical", "label": "personal data, no DPA"})
    if v["notice_passed"]:
        f.append({"key": "notice_passed", "severity": "critical", "label": "renewal notice deadline passed"})
    if v["unsigned"]:
        f.append({"key": "unsigned", "severity": "high", "label": f"{v['unsigned']} not fully signed"})
    if v["no_tfc"]:
        f.append({"key": "no_tfc", "severity": "high", "label": "no termination for convenience"})
    if v["dev_critical"] or v["dev_high"]:
        f.append({"key": "deviations", "severity": "high",
                  "label": f"{v['dev_critical'] + v['dev_high']} high/critical deviations"})
    if v["notice_soon"]:
        f.append({"key": "notice_soon", "severity": "medium", "label": "renewal notice due within 30 days"})
    if v["expiring_30"]:
        f.append({"key": "expiring_30", "severity": "medium", "label": f"{v['expiring_30']} expiring within 30 days"})
    f.sort(key=lambda x: -SEV_RANK[x["severity"]])
    return f


VENDOR_SQL = """
SELECT e.vendor,
       array_agg(DISTINCT e.category ORDER BY e.category) AS categories,
       count(*) AS contracts,
       (SELECT count(*) FROM contracts c WHERE c.vendor = e.vendor) AS documents,
       coalesce(sum(e.annual_value), 0) AS annual_value,
       coalesce(sum(e.total_value) FILTER (WHERE e.type = 'Work Order'), 0) AS work_order_value,
       count(*) FILTER (WHERE e.auto_renew) AS auto_renewals,
       count(*) FILTER (WHERE e.liability_uncapped) AS uncapped,
       count(*) FILTER (WHERE e.termination_for_convenience = false) AS no_tfc,
       count(*) FILTER (WHERE e.processes_personal_data AND NOT e.has_dpa AND e.type <> 'DPA') AS pd_no_dpa,
       count(*) FILTER (WHERE NOT e.fully_executed) AS unsigned,
       count(*) FILTER (WHERE r.days_left BETWEEN 0 AND 30) AS expiring_30,
       count(*) FILTER (WHERE r.auto_renew AND r.notice_days_left < 0) AS notice_passed,
       count(*) FILTER (WHERE r.auto_renew AND r.notice_days_left BETWEEN 0 AND 30) AS notice_soon,
       min(e.expiry_date) FILTER (WHERE e.expiry_date >= current_date) AS next_expiry,
       (SELECT count(*) FROM clause_deviations d JOIN contracts c ON c.id = d.contract_id
          WHERE c.vendor = e.vendor AND d.severity = 'critical') AS dev_critical,
       (SELECT count(*) FROM clause_deviations d JOIN contracts c ON c.id = d.contract_id
          WHERE c.vendor = e.vendor AND d.severity = 'high') AS dev_high,
       (SELECT count(*) FROM clause_deviations d JOIN contracts c ON c.id = d.contract_id
          WHERE c.vendor = e.vendor) AS deviations
FROM v_effective_terms e LEFT JOIN v_renewals r ON r.contract_id = e.contract_id
WHERE e.status = 'active' {where}
GROUP BY e.vendor ORDER BY coalesce(sum(e.annual_value), 0) DESC, e.vendor
"""


def _vendor_rows(vendor: str | None = None) -> list[dict]:
    rows = q(VENDOR_SQL.format(where="AND e.vendor = :v" if vendor else ""), **({"v": vendor} if vendor else {}))
    today = dt.date.today()
    for v in rows:
        v["flags"] = _vendor_flags(v)
        v["risk"] = v["flags"][0]["severity"] if v["flags"] else "low"
        v["next_expiry_days"] = (v["next_expiry"] - today).days if v["next_expiry"] else None
    return rows


@router.get("/vendors")
def vendors():
    return _vendor_rows()


@router.get("/vendors/{vendor}")
def vendor_profile(vendor: str):
    rows = _vendor_rows(vendor)
    if not rows:
        raise HTTPException(404, "vendor not found")
    docs = list_contracts(vendor=vendor)
    devs = q(
        """SELECT c.id AS contract_id, c.title, c.type, tc.clause_type, d.severity, d.deviation_summary
           FROM clause_deviations d JOIN contracts c ON c.id = d.contract_id
           JOIN template_clauses tc ON tc.id = d.template_clause_id WHERE c.vendor = :v""",
        v=vendor,
    )
    for d in devs:
        d["heading"] = CLAUSES[d["clause_type"]].heading
    devs.sort(key=lambda d: (-SEV_RANK[d["severity"]], d["title"]))
    upcoming = q(
        """SELECT contract_id AS id, title, type, expiry_date, notice_deadline, auto_renew, days_left, notice_days_left
           FROM v_renewals WHERE vendor = :v ORDER BY expiry_date""",
        v=vendor,
    )
    return {"summary": rows[0], "documents": docs, "deviations": devs, "upcoming": upcoming}


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard")
def dashboard():
    k = q1("""SELECT
        (SELECT count(*) FROM contracts WHERE status <> 'draft') AS contracts,
        (SELECT coalesce(sum(annual_value),0) FROM v_effective_terms WHERE status='active') AS annual_value,
        count(*) FILTER (WHERE days_left BETWEEN 0 AND 90) AS expiring_90,
        coalesce(sum(annual_value) FILTER (WHERE days_left BETWEEN 0 AND 90),0) AS expiring_90_value,
        count(*) FILTER (WHERE auto_renew AND notice_days_left <= 30) AS autorenew_notice_soon,
        count(*) FILTER (WHERE auto_renew AND notice_days_left < 0) AS autorenew_notice_passed,
        count(*) FILTER (WHERE liability_uncapped) AS uncapped
        FROM v_renewals""")
    rows = q(
        """SELECT contract_id AS id, title, vendor, category, type, owner, annual_value, auto_renew,
                  expiry_date, notice_period_days, notice_deadline, days_left, notice_days_left,
                  liability_uncapped, fully_executed
           FROM v_renewals WHERE days_left BETWEEN 0 AND 90 ORDER BY expiry_date, title"""
    )
    lanes = {
        key: {"label": label, "severity": sev, "items": [], "value": 0.0}
        for key, label, sev in (
            ("30", "Expiring in 0–30 days", "high"),
            ("60", "Expiring in 31–60 days", "medium"),
            ("90", "Expiring in 61–90 days", "low"),
        )
    }
    for r in rows:
        key = "30" if r["days_left"] <= 30 else "60" if r["days_left"] <= 60 else "90"
        r["notice_passed"] = bool(r["auto_renew"] and r["notice_days_left"] < 0)
        lanes[key]["items"].append(r)
        lanes[key]["value"] += float(r["annual_value"] or 0)
    for lane in lanes.values():
        lane["count"] = len(lane["items"])
    monthly = {
        r["m"]: r
        for r in q(
            """SELECT to_char(date_trunc('month', expiry_date), 'YYYY-MM') AS m, count(*) AS count,
                      coalesce(sum(annual_value), 0) AS value
               FROM v_renewals WHERE expiry_date >= date_trunc('month', current_date)
                 AND expiry_date < date_trunc('month', current_date) + interval '12 months' GROUP BY 1"""
        )
    }
    today = dt.date.today()
    months = []
    for n in range(12):
        y, m0 = today.year + (today.month - 1 + n) // 12, (today.month - 1 + n) % 12 + 1
        key = f"{y}-{m0:02d}"
        months.append(
            {
                "month": key,
                "label": dt.date(y, m0, 1).strftime("%b %y"),
                "count": monthly.get(key, {}).get("count", 0),
                "value": float(monthly.get(key, {}).get("value", 0)),
            }
        )
    risks = {
        "uncapped": q(
            "SELECT contract_id AS id, title, vendor FROM v_effective_terms WHERE liability_uncapped"
        ),
        "no_tfc": q(
            "SELECT contract_id AS id, title, vendor FROM v_effective_terms WHERE termination_for_convenience = false"
        ),
        "pd_without_dpa": q("""SELECT contract_id AS id, title, vendor FROM v_effective_terms
                              WHERE processes_personal_data AND NOT has_dpa AND type <> 'DPA'"""),
    }
    return {"kpis": k, "lanes": lanes, "monthly": months, "risks": risks}


# ------------------------------------------------------------------ ask
class AskIn(BaseModel):
    question: str
    demo_mode: bool = False
    contract_ids: list[int] | None = None  # scope: only these documents (None = whole portfolio)


@router.post("/ask")
def ask(body: AskIn):
    return ask_mod.answer(body.question, body.demo_mode, body.contract_ids or None)


@router.get("/ask/suggestions")
def suggestions():
    return [
        r["question"] for r in q("SELECT question FROM ask_cache ORDER BY created_at, question")
    ]


# ------------------------------------------------------------------ redline & checklist
def _sev_counts(items: list[dict]) -> dict:
    return {sv: sum(1 for i in items if i["severity"] == sv) for sv in SEV_RANK}


@router.get("/redline/documents")
def redline_documents():
    out = []
    for d in q(
        """SELECT c.id, c.title, c.vendor, c.type, c.status, c.origin, r.items
           FROM contracts c LEFT JOIN redlines r ON r.contract_id = c.id
           WHERE c.type <> 'Amendment' ORDER BY (c.status = 'draft') DESC, c.id DESC"""
    ):
        items = d.pop("items") or []
        fails = q("SELECT severity FROM check_results WHERE contract_id = :i AND status = 'fail'", i=d["id"])
        d["deviations"] = len(items)
        d["counts"] = _sev_counts(items)
        d["checks_failed"] = len(fails)
        d["check_counts"] = _sev_counts(fails)
        out.append(d)
    return out


def _redline_payload(cid: int, source: str) -> dict:
    d = q1("SELECT id, title, vendor, type, status, body_md, origin FROM contracts WHERE id = :i", i=cid)
    if not d:
        raise HTTPException(404, "document not found")
    r = q1("SELECT items FROM redlines WHERE contract_id = :i", i=cid)
    items = (r or {}).get("items") or []
    tpl = q1("SELECT t.id, t.name, t.type FROM templates t JOIN contracts c ON c.template_id = t.id WHERE c.id = :i", i=cid)
    checks = _checks(cid)
    summary = {s_: sum(1 for c in checks if c["status"] == s_) for s_ in ("pass", "fail", "na")}
    return {**d, "template": tpl, "items": items, "counts": _sev_counts(items), "source": source,
            "checklist": checks, "checklist_summary": summary,
            "checklist_fail_counts": _sev_counts([c for c in checks if c["status"] == "fail"])}


@router.get("/redline/{cid}")
def redline(cid: int):
    return _redline_payload(cid, "cached")


@router.post("/redline/{cid}/rerun")
def redline_rerun(cid: int):
    """Re-run the template comparison (Claude if a key is set) and the checklist on the stored clauses."""
    import time

    from app import pipeline as pl
    from app.db import SessionLocal as SL
    from app.models import Contract

    t0 = time.time()
    with SL() as s:
        c = s.get(Contract, cid)
        if not c:
            raise HTTPException(404, "document not found")
        rows = s.execute(text("SELECT id, clause_type, heading, text, page FROM clauses WHERE contract_id=:c ORDER BY id"), {"c": cid}).mappings().all()
        cfg = pl.load_config(s)
        mode = "llm" if llm.available() else "heuristic"
        pl.derive(s, c, [dict(r) for r in rows], cfg, pl.TEMPLATE_KEY.get(c.type, "MSA"), mode)
        s.commit()
    return {**_redline_payload(cid, mode), "elapsed_ms": int((time.time() - t0) * 1000)}


# ------------------------------------------------------------------ templates
@router.get("/templates")
def templates():
    return q("""SELECT t.id, t.name, t.type, t.version,
                  (SELECT count(*) FROM template_clauses WHERE template_id = t.id) AS clause_count,
                  (SELECT count(DISTINCT c.id) FROM contracts c WHERE c.template_id = t.id
                      AND c.type <> 'Amendment' AND c.status <> 'draft') AS contracts,
                  (SELECT count(DISTINCT d.contract_id) FROM clause_deviations d
                      JOIN contracts c ON c.id = d.contract_id WHERE c.template_id = t.id AND c.status <> 'draft') AS deviating_contracts
                FROM templates t ORDER BY t.id""")


@router.get("/templates/{tid}")
def template(tid: int):
    t = q1("SELECT id, name, type, version FROM templates WHERE id=:i", i=tid)
    if not t:
        raise HTTPException(404, "template not found")
    clauses = q("SELECT * FROM template_clauses WHERE template_id=:i ORDER BY id", i=tid)
    contracts = q(
        """SELECT id, title, vendor FROM contracts WHERE template_id=:i AND type <> 'Amendment' AND status <> 'draft'
                     ORDER BY vendor, title""",
        i=tid,
    )
    devs = q(
        """SELECT d.contract_id, d.template_clause_id, d.severity, d.deviation_summary
                FROM clause_deviations d JOIN template_clauses tc ON tc.id = d.template_clause_id
                WHERE tc.template_id = :i""",
        i=tid,
    )
    cell = {(d["contract_id"], d["template_clause_id"]): d for d in devs}
    for c in clauses:
        c["heading"] = CLAUSES[c["clause_type"]].heading
        c["variable"] = CLAUSES[c["clause_type"]].variable
        c["deviation_count"] = sum(1 for d in devs if d["template_clause_id"] == c["id"])
    matrix = [
        {"contract": c, "cells": {str(cl["id"]): cell.get((c["id"], cl["id"])) for cl in clauses}}
        for c in contracts
    ]
    return {"template": t, "clauses": clauses, "matrix": matrix}


# ------------------------------------------------------------------ admin
PRICE_PER_MTOK = {"input": 3.0, "output": 15.0}  # USD, estimate only: edit for the model in use


@router.get("/admin/usage")
def usage():
    rows = q("""SELECT purpose, model, count(*) AS calls, sum(input_tokens) AS input_tokens,
                       sum(output_tokens) AS output_tokens, round(avg(latency_ms)) AS avg_latency_ms
                FROM llm_calls GROUP BY purpose, model ORDER BY purpose""")
    for r in rows:
        r["est_cost_usd"] = round(
            (
                r["input_tokens"] * PRICE_PER_MTOK["input"]
                + r["output_tokens"] * PRICE_PER_MTOK["output"]
            )
            / 1e6,
            4,
        )
    return {
        "rows": rows,
        "total_calls": sum(r["calls"] for r in rows),
        "total_input_tokens": sum(r["input_tokens"] for r in rows),
        "total_output_tokens": sum(r["output_tokens"] for r in rows),
        "est_cost_usd": round(sum(r["est_cost_usd"] for r in rows), 4),
        "price_note": f"Estimated at ${PRICE_PER_MTOK['input']}/MTok in, ${PRICE_PER_MTOK['output']}/MTok out",
        "llm_available": bool(settings.anthropic_api_key),
    }
