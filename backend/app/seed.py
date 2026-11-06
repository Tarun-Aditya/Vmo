"""Seed pipeline: generate docs -> parse -> extract -> embed -> deviations -> redlines -> load DB.
Idempotent: truncates content tables (not llm_calls) and reloads from the generated documents."""

from __future__ import annotations

import json
import sys
import time
from datetime import date

from sqlalchemy import text

from app import deviations, embeddings, extraction
from app.config import data_path
from app.db import SessionLocal
from app.docgen.generate import generate, render_template
from app.models import (
    Clause,
    ClauseDeviation,
    Contract,
    Draft,
    FieldExtraction,
    RedlineResult,
    Template,
    TemplateClause,
)
from app.parsing import parse_document

OVERRIDABLE = {
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
}
DATE_FIELDS = {"effective_date", "expiry_date"}


def _coerce(field: str, v):
    if v is None:
        return None
    return date.fromisoformat(v) if field in DATE_FIELDS else v


def run(
    seed_date: date | None = None, extractor: str = "auto", redline_mode: str = "auto", log=print
) -> dict:
    t0 = time.time()
    seed_date = seed_date or date.today()
    root = data_path()
    manifest = generate(root, seed_date)
    log(
        f"generated {len(manifest['templates'])} templates, {len(manifest['contracts'])} "
        f"contracts, {len(manifest['drafts'])} drafts (seed date {seed_date})"
    )
    stats = dict(extractor=None, clauses=0, deviations=0, redlines=0)
    with SessionLocal() as s:
        s.execute(
            text(
                "TRUNCATE templates, template_clauses, contracts, clauses, "
                "field_extractions, clause_deviations, drafts, redline_results, "
                "ask_cache RESTART IDENTITY CASCADE"
            )
        )
        # --- templates
        tmpl_id, tclause_id = {}, {}
        for t in manifest["templates"]:
            md = (root / "docs" / t["file"]).read_text()
            row = Template(name=t["name"], type=t["type"], version="1.0", body_md=md)
            s.add(row)
            s.flush()
            tmpl_id[t["type"]] = row.id
            _, meta = render_template(t["type"])
            for m in meta:
                tc = TemplateClause(template_id=row.id, **m)
                s.add(tc)
                s.flush()
                tclause_id[(t["type"], m["clause_type"])] = tc.id
        # --- executed contracts (parents are listed before children)
        cid: dict[str, int] = {}
        for c in manifest["contracts"]:
            md = (root / "docs" / c["file"]).read_text()
            header, clauses = parse_document(md)
            fields, mode = extraction.extract(md, header, clauses, c["type"], extractor)
            stats["extractor"] = mode
            val = {f: _coerce(f, d["value"]) for f, d in fields.items()}
            row = Contract(
                title=c["title"],
                vendor=c["vendor"],
                category=c["category"],
                type=c["type"],
                template_id=tmpl_id[c["template"]],
                parent_id=cid.get(c["parent"]),
                status="active",
                owner=c["owner"],
                body_md=md,
                currency="INR",
                overrides=sorted((set(val) & OVERRIDABLE)) if c["type"] == "Amendment" else [],
                effective_date=val.get("effective_date"),
                expiry_date=val.get("expiry_date"),
                notice_period_days=val.get("notice_period_days"),
                auto_renew=bool(val.get("auto_renew")),
                annual_value=val.get("annual_value"),
                total_value=val.get("total_value"),
                payment_terms_days=val.get("payment_terms_days"),
                liability_cap_multiple=val.get("liability_cap_multiple"),
                liability_cap_text=val.get("liability_cap_text"),
                termination_for_convenience=val.get("termination_for_convenience"),
                governing_law=val.get("governing_law"),
                processes_personal_data=bool(val.get("processes_personal_data")),
                has_dpa=bool(val.get("has_dpa")),
            )
            s.add(row)
            s.flush()
            cid[c["key"]] = row.id
            vecs = embeddings.embed([f"{k['heading']}. {k['text']}" for k in clauses])
            by_type = {}
            for k, v in zip(clauses, vecs):
                cl = Clause(
                    contract_id=row.id,
                    clause_type=k["clause_type"],
                    heading=k["heading"],
                    text=k["text"],
                    page=k["page"],
                    embedding=v,
                )
                s.add(cl)
                s.flush()
                by_type[k["clause_type"]] = cl.id
            stats["clauses"] += len(clauses)
            for f, d in fields.items():
                s.add(
                    FieldExtraction(
                        contract_id=row.id,
                        field=f,
                        value=None if d["value"] is None else str(d["value"]),
                        confidence=d["confidence"],
                        source_clause_id=by_type.get(d["clause_type"]),
                        source_page=d["page"],
                    )
                )
            if c["type"] != "Amendment":
                for it in deviations.compare_document(clauses, c["template"], extractor):
                    s.add(
                        ClauseDeviation(
                            contract_id=row.id,
                            template_clause_id=tclause_id[(c["template"], it["clause_type"])],
                            deviation_summary=it["deviation"],
                            severity=it["severity"],
                        )
                    )
                    stats["deviations"] += 1
        # --- drafts + cached redlines
        for d in manifest["drafts"]:
            md = (root / "docs" / d["file"]).read_text()
            _, clauses = parse_document(md)
            row = Draft(
                title=d["title"], vendor=d["vendor"], template_id=tmpl_id[d["template"]], body_md=md
            )
            s.add(row)
            s.flush()
            items = deviations.compare_document(clauses, d["template"], redline_mode)
            s.add(RedlineResult(draft_id=row.id, items=items))
            stats["redlines"] += len(items)
        s.commit()
        s.execute(text("ANALYZE"))
    # --- cached Ask answers for demo mode (needs the committed data)
    try:
        from app import ask

        stats["ask_cached"] = ask.precompute_demo_answers(log=log)
    except ImportError:
        pass
    stats["seconds"] = round(time.time() - t0, 1)
    log("seed complete: " + json.dumps(stats))
    return stats


if __name__ == "__main__":
    args = sys.argv[1:]
    d = date.fromisoformat(args[0]) if args and args[0][0].isdigit() else None
    run(d)
