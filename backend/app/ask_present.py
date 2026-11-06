"""Turn raw tool calls into what the UI shows: result tables, headline tiles and a step-by-step
"thinking" trace. Works for every engine (Claude loop, scripted plans, offline planner)."""
from __future__ import annotations

import re

from app.docgen.library import CLAUSES

HIDE = {"contract_id", "clause_id", "id", "parent_id"}
LABELS = {
    "title": "Contract", "vendor": "Vendor", "type": "Type", "category": "Category", "owner": "Owner",
    "status": "Status", "effective_date": "Start date", "expiry_date": "End date",
    "notice_deadline": "Notice deadline", "notice_period_days": "Notice (days)",
    "annual_value": "Annual value", "total_value": "Total value",
    "total_annual_value": "Annual value", "avg_annual_value": "Average annual value",
    "payment_terms_days": "Payment terms (days)", "liability_cap_text": "Liability cap",
    "liability_cap_multiple": "Liability cap (× fees)", "governing_law": "Governing law",
    "auto_renew": "Auto-renews", "termination_for_convenience": "Termination for convenience",
    "processes_personal_data": "Processes personal data", "has_dpa": "Has DPA",
    "customer_signatory": "Signed by (Arcadia)", "customer_signed_date": "Arcadia signed on",
    "supplier_signatory": "Signed by (Supplier)", "supplier_signed_date": "Supplier signed on",
    "fully_executed": "Fully signed", "days_left": "Days left", "notice_days_left": "Notice days left",
    "contracts": "Contracts", "heading": "Clause", "page": "Page", "text": "Clause text",
    "score": "Match", "deviation_summary": "Deviation", "severity": "Severity",
    "set_by": "Set by", "nda": "NDA", "nda_expiry": "NDA end date", "msa": "Related MSA",
    "msa_effective_expiry": "MSA end date", "earliest_expiry": "First end date",
    "earliest_notice_deadline": "First notice deadline", "effective_payment_terms_days": "Effective payment terms (days)",
    "set_by_type": "Set by (type)", "auto_renewing": "Auto-renewing", "uncapped": "Uncapped",
}


def label_of(col: str) -> str:
    if col in LABELS:
        return LABELS[col]
    if col.startswith("has_") and col[4:] in CLAUSES:
        return "Fully signed" if col == "has_execution" else CLAUSES[col[4:]].heading
    return col.replace("_", " ").capitalize()


def kind_of(col: str, values: list) -> str:
    vals = [v for v in values if v is not None]
    if vals and all(isinstance(v, bool) for v in vals):
        return "bool"
    c = col.lower()
    if c.endswith("_date") or c.endswith("deadline") or c.endswith("expiry") or c.startswith("earliest_") and "notice" in c:
        return "date"
    if re.search(r"value|spend|fee|usd|cover", c) and "days" not in c and vals and all(isinstance(v, (int, float)) for v in vals):
        return "money"
    if c == "severity":
        return "severity"
    if c == "score":
        return "score"
    if vals and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals):
        return "number"
    return "text"


def table_from_sql(out: dict, title: str | None = None, max_rows: int = 200) -> dict:
    cols = out["columns"]
    cid = cols.index("contract_id") if "contract_id" in cols else (cols.index("id") if "id" in cols else None)
    show = [i for i, c in enumerate(cols) if c not in HIDE]
    columns = []
    mm = _metric_meta()
    for i in show:
        m = mm.get(cols[i])
        kind = "money" if m and m.get("unit") == "USD" else kind_of(cols[i], [r[i] for r in out["rows"]])
        label = (m["name"] + (f" ({m['unit']})" if m.get("unit") and m["unit"] != "USD" else "")) if m else label_of(cols[i])
        columns.append({"key": cols[i], "label": label, "kind": kind})
    rows = []
    for r in out["rows"][:max_rows]:
        d = {cols[i]: r[i] for i in show}
        if cid is not None and "title" in cols:
            d["_cid"] = r[cid]
        rows.append(d)
    return {"title": title, "columns": columns, "rows": rows, "row_count": out.get("row_count", len(rows))}


def table_vertical(out: dict, title: str | None, metrics: dict[str, dict] | None = None) -> dict:
    """One-row result shown as Field / Value (a document fact sheet)."""
    cols, row = out["columns"], out["rows"][0]
    rows = []
    for c, v in zip(cols, row):
        if c in HIDE:
            continue
        m = (metrics or {}).get(c)
        kind = "money" if m and m.get("kind") == "money" else kind_of(c, [v])
        rows.append({"field": m["name"] if m else label_of(c), "value": v, "kind": kind, "unit": (m or {}).get("unit")})
    return {"title": title, "kv": True, "columns": [{"key": "field", "label": "Field", "kind": "text"}, {"key": "value", "label": "Value", "kind": "text"}],
            "rows": rows, "row_count": len(rows), "_cid": row[cols.index("contract_id")] if "contract_id" in cols else None}


def table_from_hits(hits: list[dict]) -> dict:
    columns = [{"key": "title", "label": "Contract", "kind": "text"},
               {"key": "heading", "label": "Clause", "kind": "text"},
               {"key": "page", "label": "Page", "kind": "number"},
               {"key": "text", "label": "Clause text", "kind": "quote"},
               {"key": "score", "label": "Match", "kind": "score"}]
    rows = [{**{k: h[k] for k in ("title", "heading", "page", "text", "score")}, "_cid": h["contract_id"]}
            for h in hits]
    return {"title": "Matching clauses (semantic search)", "columns": columns, "rows": rows,
            "row_count": len(rows)}


def _metric_meta() -> dict[str, dict]:
    try:
        from sqlalchemy import text

        from app.db import SessionLocal

        with SessionLocal() as s:
            return {r["key"]: dict(r) for r in s.execute(text("SELECT key, name, kind, unit FROM metrics")).mappings()}
    except Exception:
        return {}


def _ok_sql(calls):
    return [c for c in calls if c["name"] == "run_sql" and "rows" in c["output"] and "error" not in c["output"]]


def tiles_from_calls(calls: list[dict]) -> tuple[list[dict], dict | None]:
    """First single-row, all-numeric SQL result becomes headline tiles. Returns (tiles, that call)."""
    for c in _ok_sql(calls):
        if c.get("no_tiles"):
            continue
        o = c["output"]
        if len(o["rows"]) == 1 and len(o["columns"]) <= 4 and all(
                isinstance(v, (int, float)) and not isinstance(v, bool) or v is None for v in o["rows"][0]):
            tiles = [{"label": label_of(col), "kind": kind_of(col, [o["rows"][0][i]]) if
                      kind_of(col, [o["rows"][0][i]]) in ("money",) else "number", "value": o["rows"][0][i]}
                     for i, col in enumerate(o["columns"])]
            return tiles, c
    return [], None


def _label_for(o: dict) -> str | None:
    cols = o["columns"]
    if "title" in cols or "contract_id" in cols:
        return "Contracts"
    text_cols = [c for c in cols if c not in HIDE and not any(isinstance(r[cols.index(c)], (int, float)) and not isinstance(r[cols.index(c)], bool) for r in o["rows"][:1])]
    return f"Breakdown by {label_of(text_cols[0]).lower()}" if text_cols and len(o["rows"]) > 1 else None


def plain(t: str) -> str:
    """Written answers are prose: strip markdown the model may add (the tables carry the detail)."""
    lines = [ln for ln in t.splitlines() if not ln.strip().startswith("|")]
    out, items = [], []
    for ln in lines:
        m = re.match(r"^\s*(?:[-*•]|\d+[.)])\s+(.*)$", ln)
        if m:
            items.append(m.group(1).strip().rstrip(".;"))
        elif ln.strip():
            out.append(ln.strip())
    s = " ".join(out)
    if items:
        s = (s.rstrip(":") + ": " if s else "") + "; ".join(items) + "."
    return re.sub(r"\s+", " ", re.sub(r"[*_`]{1,3}", "", s)).strip()


def build_tables(calls: list[dict], tile_call: dict | None) -> list[dict]:
    sql = [c for c in _ok_sql(calls) if c is not tile_call and not c.get("no_tiles")]
    chosen = [c for c in sql if c.get("display")]
    if not chosen:      # free-form (Claude) answers: show the grouped breakdown(s) and the final list, each as its own table
        picked: list[dict] = []
        for c in sql:
            o = c["output"]
            if not o["rows"]:
                continue
            picked = [p for p in picked if p["output"]["columns"] != o["columns"]]      # a re-run of the same shape replaces the older one
            picked.append(c)
        chosen = [{**c, "label": c.get("label") or _label_for(c["output"])} for c in picked[-3:]]
    tables = [
        (table_vertical(c["output"], c.get("label"), _metric_meta()) if c.get("vertical") else table_from_sql(c["output"], c.get("label")))
        for c in chosen
        if c["output"]["rows"]
    ]
    hits, seen = [], set()
    for c in calls:
        if c["name"] == "search_clauses":
            for h in c["output"].get("hits", []):
                if h["clause_id"] not in seen:
                    seen.add(h["clause_id"])
                    hits.append(h)
    if hits:
        tables.append(table_from_hits(hits))
    return tables


def build_thinking(calls: list[dict], plan_steps: list[dict] | None, notes: list[str] | None) -> list[dict]:
    steps: list[dict] = list(plan_steps or [])
    for n in notes or []:
        if n.strip():
            steps.append({"title": "Reasoning", "detail": n.strip()})
    for c in calls:
        o, inp = c["output"], c["input"]
        if c["name"] == "run_sql":
            st = {"title": c.get("label") or "Translated the question to SQL and ran it", "sql": inp["query"]}
            if "error" in o:
                st["error"] = o["error"]
                st["detail"] = "The query failed, so the error was fed back to correct it."
            else:
                st["detail"] = f"{o['row_count']} row(s) returned"
                keep = [i for i, x in enumerate(o["columns"]) if x not in HIDE]
                st["columns"] = [label_of(o["columns"][i]) for i in keep]
                st["rows"] = [[r[i] for i in keep] for r in o["rows"][:20]]
                st["row_count"] = o["row_count"]
        elif c["name"] == "search_clauses":
            flt = ", ".join(f"{k}={v}" for k, v in inp.items() if k not in ("query", "top_k") and v)
            st = {"title": "Searched clause text semantically",
                  "detail": f"Query: “{inp['query']}”" + (f" · filters: {flt}" if flt else "")
                  + f" · {len(o.get('hits', []))} clause(s) retrieved"}
        else:
            st = {"title": f"Looked up contract #{inp.get('id')}", "detail": "Fetched fields and effective terms."}
        steps.append(st)
    steps.append({"title": "Composed the answer", "detail": "Summarised the results above into the answer and tables."})
    return steps


def finalize(res: dict) -> dict:
    calls = res["tool_calls"]
    if res.get("answer") and any(c["name"] in ("run_sql", "search_clauses", "get_contract") for c in calls):
        res["answer"] = plain(res["answer"])
    tiles, tile_call = tiles_from_calls(calls)
    res["tiles"] = tiles
    res["tables"] = build_tables(calls, tile_call)
    res["thinking"] = build_thinking(calls, res.pop("plan_steps", None), res.pop("notes", None))
    return res
