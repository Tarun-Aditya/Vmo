"""Ask assistant: Claude tool-use loop over run_sql / search_clauses / get_contract, with a
deterministic scripted fallback (offline demo) and a cache for demo mode."""

from __future__ import annotations

import datetime as dt
import decimal
import json
import re
import time
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, text

from app import embeddings, llm
from app.config import settings
from app.db import SessionLocal

MAX_ROWS = 200
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|copy|" r"vacuum|call)\b", re.I
)

TOOLS = [
    {
        "name": "run_sql",
        "description": "Run one read-only SELECT (or WITH ... SELECT) against the "
        "contract database. Results are limited to 200 rows. Use for counts, sums, filters, dates.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "search_clauses",
        "description": "Semantic search over clause text across all "
        "contracts. Use for questions about wording or what a contract says. Returns the closest "
        "clauses with contract title, clause heading and page.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "clause_type": {"type": "string"},
                "vendor": {"type": "string", "description": "substring of vendor name"},
                "top_k": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_contract",
        "description": "Fetch one contract's fields and effective terms by id.",
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
    },
]


@lru_cache
def _ro_engine():
    return create_engine(settings.readonly_database_url, pool_pre_ping=True)


def _jsonable(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return v


# --------------------------------------------------------------------------- tools
def run_sql(query: str) -> dict:
    q = query.strip().rstrip(";").strip()
    if ";" in q:
        return {"error": "Only a single statement is allowed."}
    if not re.match(r"^(select|with)\b", q, re.I) or FORBIDDEN.search(q):
        return {"error": "Only read-only SELECT queries are allowed."}
    try:
        with _ro_engine().connect() as c:
            c.exec_driver_sql("SET TRANSACTION READ ONLY")
            # '%' must be doubled: the driver would otherwise read LIKE patterns as placeholders
            res = c.exec_driver_sql(
                f"SELECT * FROM ({q.replace('%', '%%')}) AS _q LIMIT {MAX_ROWS}"
            )
            cols = list(res.keys())
            rows = [[_jsonable(v) for v in r] for r in res.fetchall()]
    except Exception as e:  # surface the DB error so the model can fix its SQL
        return {"error": str(getattr(e, "orig", e)).strip().splitlines()[0]}
    return {
        "columns": cols,
        "rows": rows,
        "row_count": len(rows),
        "truncated": len(rows) == MAX_ROWS,
    }


def search_clauses(
    query: str, clause_type: str | None = None, vendor: str | None = None, top_k: int = 5
) -> dict:
    vec = embeddings.embed([query])[0]
    where, params = [], {"v": str(vec), "k": max(1, min(int(top_k or 5), 15))}
    if clause_type:
        where.append("cl.clause_type = :ct")
        params["ct"] = clause_type
    if vendor:
        where.append("c.vendor ILIKE :vendor")
        params["vendor"] = f"%{vendor}%"
    sql = f"""SELECT cl.id AS clause_id, c.id AS contract_id, c.title, c.vendor, c.type,
                     cl.clause_type, cl.heading, cl.page, cl.text,
                     1 - (cl.embedding <=> CAST(:v AS vector)) AS score
              FROM clauses cl JOIN contracts c ON c.id = cl.contract_id
              {"WHERE " + " AND ".join(where) if where else ""}
              ORDER BY cl.embedding <=> CAST(:v AS vector) LIMIT :k"""
    with SessionLocal() as s:
        rows = s.execute(text(sql), params).mappings().all()
    hits = [{k: _jsonable(v) for k, v in r.items()} for r in rows]
    for h in hits:
        h["score"] = round(h["score"], 3)
    return {"hits": hits}


def get_contract(id: int) -> dict:
    with SessionLocal() as s:
        row = s.execute(text("SELECT * FROM contracts WHERE id=:i"), {"i": id}).mappings().first()
        if not row:
            return {"error": f"No contract with id {id}"}
        eff = (
            s.execute(text("SELECT * FROM v_effective_terms WHERE contract_id=:i"), {"i": id})
            .mappings()
            .first()
        )
    drop = {"body_md", "created_at"}
    return {
        "contract": {k: _jsonable(v) for k, v in row.items() if k not in drop},
        "effective_terms": {k: _jsonable(v) for k, v in (eff or {}).items()},
    }


def execute_tool(name: str, args: dict) -> dict:
    fn = {"run_sql": run_sql, "search_clauses": search_clauses, "get_contract": get_contract}[name]
    try:
        return fn(**args)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------- LLM loop
def build_system() -> str:
    schema = (Path(__file__).parent / "prompts" / "schema.md").read_text()
    with SessionLocal() as s:
        samples = {
            "vendors": [
                r[0] for r in s.execute(text("SELECT DISTINCT vendor FROM contracts ORDER BY 1"))
            ],
            "categories": [
                r[0] for r in s.execute(text("SELECT DISTINCT category FROM contracts ORDER BY 1"))
            ],
        }
    schema += f"\nSample values: vendors={samples['vendors']}; categories={samples['categories']}"
    return llm.prompt("ask_system").format(today=dt.date.today().isoformat(), schema=schema)


def ask_llm(question: str, max_turns: int = 8) -> dict:
    system, calls, sql_errors = build_system(), [], 0
    messages = [{"role": "user", "content": question}]
    answer = ""
    for _ in range(max_turns):
        resp = llm.create(
            "ask",
            model=settings.model_ask,
            max_tokens=2000,
            system=system,
            tools=TOOLS,
            messages=messages,
        )
        if resp.stop_reason != "tool_use":
            answer = "".join(b.text for b in resp.content if b.type == "text")
            break
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for b in (b for b in resp.content if b.type == "tool_use"):
            out = execute_tool(b.name, b.input)
            calls.append({"name": b.name, "input": b.input, "output": out})
            is_err = "error" in out
            sql_errors += is_err and b.name == "run_sql"
            content = json.dumps(out)
            if is_err and b.name == "run_sql" and sql_errors > 1:
                content += " (This is the second SQL error: do not retry; explain what went wrong.)"
            results.append(
                {"type": "tool_result", "tool_use_id": b.id, "content": content, "is_error": is_err}
            )
        messages.append({"role": "user", "content": results})
    return {"answer": answer or "I could not complete that question.", "tool_calls": calls}


# --------------------------------------------------------------------------- public API
def norm_key(q: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", q.lower()).strip()


def citations(calls: list[dict]) -> list[dict]:
    seen, out = set(), []
    for c in calls:
        for h in c["output"].get("hits", []):
            if h["clause_id"] not in seen:
                seen.add(h["clause_id"])
                out.append(
                    {
                        k: h[k]
                        for k in (
                            "contract_id",
                            "title",
                            "heading",
                            "page",
                            "clause_type",
                            "text",
                            "score",
                        )
                    }
                )
    return out


def answer(question: str, demo_mode: bool = False) -> dict:
    t0 = time.time()
    if demo_mode:
        with SessionLocal() as s:
            row = s.execute(
                text("SELECT response, source FROM ask_cache WHERE question_key=:k"),
                {"k": norm_key(question)},
            ).first()
        if row:
            return {
                **row[0],
                "source": "cache",
                "cached_from": row[1],
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
    if llm.available():
        res, source = ask_llm(question), "llm"
    else:
        from app import ask_nl, ask_scripted

        res = ask_scripted.answer(question)
        source = "scripted"
        if not res:
            res, source = ask_nl.answer(question), "offline-planner"
        if not res:
            source = "none"
            res = {
                "answer": "I couldn't map that question without Claude. Offline I can answer the "
                "preloaded demo questions plus counts, totals and lists of contracts by time "
                "window (e.g. next quarter, next 60 days), type, category, vendor, owner, "
                "auto-renewal, uncapped liability or DPA status. Set ANTHROPIC_API_KEY for "
                "free-form questions.",
                "tool_calls": [],
            }
    res["citations"] = citations(res["tool_calls"])
    res.update(question=question, source=source, elapsed_ms=int((time.time() - t0) * 1000))
    return res


def precompute_demo_answers(log=print) -> int:
    import yaml

    path = (
        next(
            p
            for p in (Path("/evals"), Path(__file__).parents[2] / "evals")
            if (p / "questions.yaml").exists()
        )
        / "questions.yaml"
    )
    qs = yaml.safe_load(path.read_text())
    n = 0
    with SessionLocal() as s:
        s.execute(text("DELETE FROM ask_cache"))
        s.commit()
    for q in qs:
        res = answer(q["question"], demo_mode=False)
        with SessionLocal() as s:
            s.execute(
                text("INSERT INTO ask_cache VALUES (:k,:q,CAST(:r AS jsonb),:src,now())"),
                {
                    "k": norm_key(q["question"]),
                    "q": q["question"],
                    "r": json.dumps(res),
                    "src": res["source"],
                },
            )
            s.commit()
        n += 1
    log(f"cached {n} demo answers")
    return n
