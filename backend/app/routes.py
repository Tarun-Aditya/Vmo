"""REST API for the POC frontend."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import ask as ask_mod
from app import deviations, llm
from app.config import settings
from app.db import SessionLocal
from app.docgen.library import CLAUSES, KEY_CLAUSES, TEMPLATES
from app.parsing import parse_document

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
    sig = {
        k: c[k]
        for k in (
            "customer_signatory", "customer_signed_date", "supplier_signatory",
            "supplier_signed_date", "fully_executed",
        )
    }
    return {
        "signatures": sig,
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


def _cell(ct, clause, expected, doc_name, tpl_name, signed=None, draft=False) -> dict:
    heading = CLAUSES[ct].heading
    if ct == "execution":
        present = bool(signed) and not draft
        if draft:
            note = "Draft: not signed or executed."
        elif present:
            note = None
        elif clause:
            note = "Not fully signed. " + clause["text"]
        else:
            note = f"No signature block found in this {doc_name}."
    else:
        present = clause is not None
        note = None
        if not present:
            note = f"No {heading} clause found in this document. " + (
                f"The standard {tpl_name} template includes one, so this is a gap."
                if expected
                else f"It is not part of the standard {tpl_name} template."
            )
    return {
        "present": present,
        "expected": expected,
        "heading": heading,
        "page": clause["page"] if clause else None,
        "text": clause["text"][:420] if clause else None,
        "note": note,
    }


@router.get("/clause-matrix")
def clause_matrix():
    """Every document (rows) x key clause (columns): present or absent, with a citation."""
    cols = [{"key": c, "label": SHORT.get(c, CLAUSES[c].heading)} for c in KEY_CLAUSES]
    clause_idx = {
        (c["contract_id"], c["clause_type"]): c
        for c in q("SELECT contract_id, clause_type, heading, text, page FROM clauses")
    }
    rows = []
    for c in q(
        """SELECT c.id, c.title, c.vendor, c.type, c.fully_executed, t.type AS tpl, t.name AS tpl_name
           FROM contracts c JOIN templates t ON t.id = c.template_id
           WHERE c.type <> 'Amendment'
           ORDER BY c.vendor, CASE c.type WHEN 'MSA' THEN 0 WHEN 'SOW' THEN 1 WHEN 'Work Order' THEN 2 ELSE 3 END, c.title"""
    ):
        exp = set(TEMPLATES[c["tpl"]]["clauses"])
        cells = {
            ct: _cell(ct, clause_idx.get((c["id"], ct)), ct in exp, c["type"], c["tpl_name"], c["fully_executed"])
            for ct in KEY_CLAUSES
        }
        rows.append({"id": c["id"], "title": c["title"], "vendor": c["vendor"], "type": c["type"],
                     "kind": "contract", "cells": cells})
    draft_rows = []
    for d in q(
        """SELECT d.id, d.title, d.vendor, d.body_md, t.type AS tpl, t.name AS tpl_name
           FROM drafts d JOIN templates t ON t.id = d.template_id ORDER BY d.id"""
    ):
        _, cl = parse_document(d["body_md"])
        idx = {c["clause_type"]: c for c in cl}
        exp = set(TEMPLATES[d["tpl"]]["clauses"])
        cells = {
            ct: _cell(ct, idx.get(ct), ct in exp, "draft", d["tpl_name"], False, draft=True)
            for ct in KEY_CLAUSES
        }
        draft_rows.append({"id": d["id"], "title": d["title"], "vendor": d["vendor"],
                           "type": d["tpl"], "kind": "draft", "cells": cells})
    for r in rows + draft_rows:
        r["present_count"] = sum(1 for c in r["cells"].values() if c["present"])
        r["gap_count"] = sum(
            1
            for ct, c in r["cells"].items()
            if not c["present"] and c["expected"] and not (r["kind"] == "draft" and ct == "execution")
        )
    totals = {ct: sum(1 for r in rows if r["cells"][ct]["present"]) for ct in KEY_CLAUSES}
    return {
        "columns": cols,
        "groups": [
            {"name": "Executed contracts", "rows": rows},
            {"name": "Vendor drafts (not yet executed)", "rows": draft_rows},
        ],
        "totals": totals,
        "executed_count": len(rows),
    }


# ------------------------------------------------------------------ dashboard
@router.get("/dashboard")
def dashboard():
    k = q1("""SELECT
        (SELECT count(*) FROM contracts) AS contracts,
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


@router.post("/ask")
def ask(body: AskIn):
    return ask_mod.answer(body.question, body.demo_mode)


@router.get("/ask/suggestions")
def suggestions():
    return [
        r["question"] for r in q("SELECT question FROM ask_cache ORDER BY created_at, question")
    ]


# ------------------------------------------------------------------ redline
def _draft_payload(did: int, items: list[dict], source: str):
    d = q1("SELECT id, title, vendor, template_id, body_md FROM drafts WHERE id=:i", i=did)
    counts = {s: sum(1 for i in items if i["severity"] == s) for s in SEV_RANK}
    tpl = q1("SELECT id, name, type FROM templates WHERE id=:t", t=d["template_id"])
    return {**d, "template": tpl, "items": items, "counts": counts, "source": source}


@router.get("/drafts")
def drafts():
    out = []
    for d in q("""SELECT d.id, d.title, d.vendor, t.type AS template_type, r.items
                  FROM drafts d JOIN templates t ON t.id = d.template_id
                  LEFT JOIN redline_results r ON r.draft_id = d.id ORDER BY d.id"""):
        items = d.pop("items") or []
        d["counts"] = {s: sum(1 for i in items if i["severity"] == s) for s in SEV_RANK}
        d["deviations"] = len(items)
        out.append(d)
    return out


@router.get("/drafts/{did}/redline")
def redline(did: int):
    r = q1("SELECT items FROM redline_results WHERE draft_id=:i", i=did)
    if not r:
        raise HTTPException(404, "draft not found")
    return _draft_payload(did, r["items"], "cached")


@router.post("/drafts/{did}/redline/rerun")
def redline_rerun(did: int):
    d = q1(
        """SELECT d.body_md, t.type FROM drafts d JOIN templates t ON t.id = d.template_id
              WHERE d.id=:i""",
        i=did,
    )
    if not d:
        raise HTTPException(404, "draft not found")
    _, clauses = parse_document(d["body_md"])
    mode = "llm" if llm.available() else "heuristic"
    import json
    import time

    t0 = time.time()
    items = deviations.compare_document(clauses, d["type"], mode)
    with SessionLocal() as s:
        s.execute(
            text("""UPDATE redline_results SET items = CAST(:it AS jsonb), created_at = now()
                          WHERE draft_id=:i"""),
            {"it": json.dumps(items), "i": did},
        )
        s.commit()
    return {**_draft_payload(did, items, mode), "elapsed_ms": int((time.time() - t0) * 1000)}


# ------------------------------------------------------------------ templates
@router.get("/templates")
def templates():
    return q("""SELECT t.id, t.name, t.type, t.version,
                  (SELECT count(*) FROM template_clauses WHERE template_id = t.id) AS clause_count,
                  (SELECT count(DISTINCT c.id) FROM contracts c WHERE c.template_id = t.id
                      AND c.type <> 'Amendment') AS contracts,
                  (SELECT count(DISTINCT d.contract_id) FROM clause_deviations d
                      JOIN contracts c ON c.id = d.contract_id WHERE c.template_id = t.id) AS deviating_contracts
                FROM templates t ORDER BY t.id""")


@router.get("/templates/{tid}")
def template(tid: int):
    t = q1("SELECT id, name, type, version FROM templates WHERE id=:i", i=tid)
    if not t:
        raise HTTPException(404, "template not found")
    clauses = q("SELECT * FROM template_clauses WHERE template_id=:i ORDER BY id", i=tid)
    contracts = q(
        """SELECT id, title, vendor FROM contracts WHERE template_id=:i AND type <> 'Amendment'
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
