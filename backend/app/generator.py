"""Create a new contract from a standard template: fill the template's clauses with the chosen
parameters, let the user edit the text, then drop it into the inbox so the pipeline extracts it
and runs the pre-signature checklist. Also a dry-run analyser for any text."""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import text

from app import deviations, kcc, pipeline
from app.db import SessionLocal
from app.docgen.generate import _layout, inr, long_date
from app.docgen.library import CLAUSES, CUSTOMER, TEMPLATES, clause_text
from app.parsing import parse_document

DOC_TYPE = {"MSA": "MSA", "SOW": "SOW", "WO": "Work Order", "NDA": "NDA", "SaaS": "SaaS", "DPA": "DPA"}
PARENT_TYPE = {"SOW": "MSA", "WO": "SOW", "DPA": "SaaS", "NDA": "MSA"}
DEFAULTS = dict(term_months=12, auto_renew=False, notice_days=60, payment_terms_days=45, liability_cap=1, tfc_notice_days=30,
                warranty_days=90, insurance_cover_usd=5_000_000, governing_law="New York", confidentiality_years=3, sla=99.9,
                personal_data=False, subjects="customers", annual_fees=0, fixed_fee=0, scope="", owner="Unassigned")


def forms() -> list[dict]:
    """What the UI shows: one entry per template with its fields."""
    common = ["vendor", "title", "effective_date", "term_months", "owner", "category"]
    legal = ["governing_law", "payment_terms_days", "liability_cap", "tfc_notice_days"]
    spec = {
        "MSA": common + ["auto_renew", "notice_days"] + legal + ["warranty_days", "insurance_cover_usd"],
        "SOW": common + ["parent_id", "scope", "annual_fees", "payment_terms_days"],
        "WO": common + ["parent_id", "scope", "fixed_fee", "payment_terms_days"],
        "NDA": common + ["parent_id", "confidentiality_years", "governing_law"],
        "SaaS": common + ["scope", "annual_fees", "auto_renew", "notice_days", "sla", "personal_data", "subjects"] + legal,
        "DPA": common + ["parent_id"],
    }
    return [{"template": k, "name": TEMPLATES[k]["name"], "type": DOC_TYPE[k], "parent_type": PARENT_TYPE.get(k),
             "clauses": len(TEMPLATES[k]["clauses"]), "fields": spec[k],
             "clause_keys": [c for c in TEMPLATES[k]["clauses"] if c != "dpa_reference"]} for k in TEMPLATES]


def clause_library() -> list[dict]:
    """Every clause the platform knows, with a short standard-text preview, for the clause picker."""
    out = []
    for key, c in CLAUSES.items():
        try:
            prev = clause_text(key, "Agreement", {})
        except Exception:
            prev = ""
        out.append({"key": key, "heading": c.heading, "preview": " ".join(prev.split())[:160],
                    "in_templates": [t for t, d in TEMPLATES.items() if key in d["clauses"]]})
    return sorted(out, key=lambda x: x["heading"])


def _add_months(d: date, n: int) -> date:
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    for day in (d.day, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def _num(x) -> str:
    return f"{float(x):g}"


def build(tk: str, p: dict) -> dict:
    p = {**DEFAULTS, **{k: v for k, v in p.items() if v not in (None, "")}}
    if tk not in TEMPLATES:
        raise ValueError(f"unknown template {tk}")
    if not p.get("vendor"):
        raise ValueError("vendor is required")
    doc, dtype = TEMPLATES[tk]["doc"], DOC_TYPE[tk]
    eff = date.fromisoformat(p["effective_date"]) if p.get("effective_date") else date.today()
    exp = _add_months(eff, int(p["term_months"]))
    parent = None
    if p.get("parent_id"):
        with SessionLocal() as s:
            parent = s.execute(text("SELECT id, title, effective_date, type, parent_id, category FROM contracts WHERE id=:i"), {"i": int(p["parent_id"])}).mappings().first()
            grand = s.execute(text("SELECT title, effective_date FROM contracts WHERE id=:i"), {"i": parent["parent_id"]}).mappings().first() if parent and parent["parent_id"] else None
    else:
        grand = None
    annual = int(p["annual_fees"] or 0)
    total = int(p["fixed_fee"] or 0) if tk == "WO" else int(annual * int(p["term_months"]) / 12)
    scope = p["scope"] or f"Services to be described for {p['vendor']}."
    law = p["governing_law"]
    d1, d2, d3 = eff + timedelta(days=14), eff + timedelta(days=min(90, (exp - eff).days // 2)), eff + timedelta(days=min(180, max((exp - eff).days - 14, 30)))
    cy = int(p["confidentiality_years"])
    ctx = dict(
        effective_date=long_date(eff), expiry_date=long_date(exp), annual_value=inr(annual), total_value=inr(total), scope_text=scope,
        notice_period_days=p["notice_days"], payment_terms_days=int(p["payment_terms_days"]), cap=_num(p["liability_cap"]),
        tfc_notice_days=int(p["tfc_notice_days"]), warranty_days=int(p["warranty_days"]),
        insurance_cover=f"USD {inr(int(p['insurance_cover_usd']))}", governing_law=law, venue="New York County" if law == "New York" else law,
        conf_period=f"{cy} year{'s' if cy != 1 else ''}", sla=_num(p["sla"]), dpa_date=long_date(eff + timedelta(days=14)),
        execution_text="Signature blocks: [Customer signatory: to be signed] [Supplier signatory: to be signed]. This document has not been executed.",
        data_scope_text=(f"The services involve the processing of personal data of the Customer's {p['subjects']}." if p["personal_data"]
                         else "The services do not involve the processing of personal data."),
        deliverables_text=(f"Milestone 1: mobilisation and delivery plan by {long_date(d1)}. Milestone 2: core delivery by {long_date(d2)}. "
                           f"Milestone 3: handover and written acceptance by {long_date(d3)}."),
        msa_reference_text=(f"This SOW is issued under the Master Services Agreement dated {long_date(parent['effective_date'])} between the parties "
                            f"({parent['title']}). Capitalised terms have the meaning given in that agreement." if parent and tk == "SOW"
                            else "This SOW is issued under the Master Services Agreement between the parties. Capitalised terms have the meaning given in that agreement."),
        sow_reference_text=(f"This Work Order is issued under {parent['title']} (effective {long_date(parent['effective_date'])})"
                            + (f" and the Master Services Agreement dated {long_date(grand['effective_date'])}." if grand else ".") if parent and tk == "WO"
                            else "This Work Order is issued under the Statement of Work and the Master Services Agreement between the parties."),
    )
    if tk == "DPA":
        ctx["scope_text"] = (f"This DPA supplements the {parent['title']} and applies to all personal data the Supplier processes on behalf of the Customer."
                             if parent else "This DPA applies to all personal data the Supplier processes on behalf of the Customer.")
    seq = []
    keys = [c for c in (p.get("clauses") or TEMPLATES[tk]["clauses"]) if c in CLAUSES]
    if "execution" in keys:                      # signature block always closes the document
        keys = [c for c in keys if c != "execution"] + ["execution"]
    for c in keys:
        if c == "dpa_reference":
            continue
        variant = "auto" if c == "renewal" and p["auto_renew"] else None
        seq.append((CLAUSES[c].heading, clause_text(c, doc, ctx, variant)))
    short = " ".join(scope.split()[:6]) if tk in ("SOW", "WO") and p["scope"] else ""
    title = p.get("title") or " – ".join(x for x in (TEMPLATES[tk]["name"], short, p["vendor"].replace(" Inc", "").replace(" LLP", "").replace(" Ltd", "")) if x)
    ref = f"ARC-{tk}-NEW-{date.today():%y%m%d}"
    header = [f'**Parties:** {CUSTOMER} (the "Customer") and {p["vendor"]} (the "Supplier")', f"**Effective Date:** {long_date(eff)}",
              f"**Document Type:** {dtype}", f"**Reference:** {ref}", "**Status:** DRAFT prepared from the standard template - not executed"]
    md = _layout(title, header, seq)
    category = p.get("category") or (parent["category"] if parent else "Uncategorised")
    sidecar = {"vendor": p["vendor"], "category": category, "owner": p["owner"], "status": "draft", "template": tk,
               "parent_title": parent["title"] if parent else None, "origin": "generated"}
    return {"title": title, "md": md, "doc_type": dtype, "sidecar": sidecar}


def dry_run(md: str, status: str = "draft") -> dict:
    """Analyse text without saving: classify, extract values, run the checklist, compare to the template."""
    with SessionLocal() as s:
        cfg = pipeline.load_config(s)
        s.rollback()
    header, clauses = parse_document(md, lambda h, t: kcc.classify(h, t, cfg["kcc"]))
    meta = pipeline.infer_metadata(md, header, clauses, {})
    vals = kcc.extract_metrics(clauses, cfg["metrics"], cfg["kcc"])
    res = kcc.evaluate_rules(meta["type"], status, clauses, vals, cfg["metrics"], cfg["rules"], False)
    rules = {r["key"]: r for r in cfg["rules"]}
    for r in res:
        r["name"] = rules[r["rule_key"]]["name"]
        r["suggested_text"] = rules[r["rule_key"]]["suggested_text"]
    res.sort(key=lambda r: ({"fail": 0, "pass": 1, "na": 2}[r["status"]], {"critical": 0, "high": 1, "medium": 2, "low": 3}[r["severity"]]))
    devs = deviations.compare_document(clauses, meta["template_key"]) if meta["type"] != "Amendment" else []
    return {"type": meta["type"], "vendor": meta["vendor"], "clauses": len(clauses), "checks": res,
            "summary": {k: sum(1 for r in res if r["status"] == k) for k in ("pass", "fail", "na")}, "deviations": len(devs)}


def create(tk: str, p: dict, md: str | None = None) -> dict:
    b = build(tk, p)
    md = md or b["md"]
    slug = re.sub(r"[^a-z0-9]+", "-", b["title"].lower()).strip("-")[:80] + f"-{date.today():%y%m%d%H%M%S}"
    path = pipeline.add_document(f"{slug}.md", md, b["sidecar"], subdir="generated")
    res = pipeline.run_pipeline("create", only=[path])
    if res.get("status") == "busy":
        return {"status": "busy", "message": res["message"]}
    with SessionLocal() as s:
        root = pipeline.inbox_path(s)
        row = s.execute(text("SELECT id, title FROM contracts WHERE source_path=:p"), {"p": str(path.relative_to(root))}).first()
        fails = [dict(r) for r in s.execute(text("SELECT r.name, cr.severity, cr.actual, cr.expected FROM check_results cr JOIN checklist_rules r ON r.key=cr.rule_key WHERE cr.contract_id=:c AND cr.status='fail'"), {"c": row[0]}).mappings()] if row else []
    return {"status": "created", "contract_id": row[0] if row else None, "title": row[1] if row else b["title"], "failed_checks": fails, "run": res}
