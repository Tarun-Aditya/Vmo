"""Admin API: pipeline (frequency, run now, history, add document), KCC library, values & limits,
redline checklist, New Contract generator, document list for the Ask scope."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app import generator, kcc, pipeline, scheduler
from app.db import SessionLocal

router = APIRouter(prefix="/api")
SEV = ["low", "medium", "high", "critical"]
SLUG = re.compile(r"^[a-z][a-z0-9_]{1,48}$")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def run_sql(sql: str, **p):
    with SessionLocal() as s:
        s.execute(text(sql), p)
        s.commit()


def _reprocess():
    return pipeline.reprocess_all()


# ------------------------------------------------------------------ status / documents
@router.get("/status")
def status():
    cfg = rows("SELECT enabled, interval_minutes, last_run_at, next_run_at FROM pipeline_config WHERE key='contracts'")[0]
    last = rows("SELECT id, started_at, finished_at, trigger, pipeline, status, scanned, new_docs, updated, unchanged, failed FROM pipeline_runs ORDER BY id DESC LIMIT 1")
    docs = rows("SELECT status, count(*) AS n FROM contracts GROUP BY status")
    return {"running": pipeline._lock.locked(), "config": cfg, "last_run": last[0] if last else None,
            "documents": {d["status"]: d["n"] for d in docs}, "now": datetime.now(timezone.utc).isoformat()}


@router.get("/documents")
def documents(search: str | None = None):
    """Light list for the Ask scope picker."""
    return rows("""SELECT id, title, vendor, type, status FROM contracts
                   WHERE (CAST(:s AS text) IS NULL OR title ILIKE :p OR vendor ILIKE :p OR type ILIKE :p)
                   ORDER BY (status='draft'), vendor, CASE type WHEN 'MSA' THEN 0 WHEN 'SOW' THEN 1 WHEN 'Work Order' THEN 2 ELSE 3 END, title""",
                s=search, p=f"%{search}%" if search else None)


# ------------------------------------------------------------------ pipeline
class PipelineCfg(BaseModel):
    enabled: bool = True
    interval_minutes: int


@router.get("/admin/pipeline")
def pipeline_get():
    st = status()
    with SessionLocal() as s:
        st["inbox"] = str(pipeline.inbox_path(s))
    st["inbox_files"] = len(pipeline.scan(__import__("pathlib").Path(st["inbox"])))
    return st


@router.put("/admin/pipeline")
def pipeline_put(c: PipelineCfg):
    if not 1 <= c.interval_minutes <= 60 * 24 * 7:
        raise HTTPException(422, "interval must be between 1 minute and 7 days")
    with SessionLocal() as s:
        scheduler.set_interval(s, c.interval_minutes, c.enabled)
        s.commit()
    return pipeline_get()


@router.post("/admin/pipeline/run")
def pipeline_run():
    if pipeline._lock.locked():
        return {"started": False, "message": "a run is already in progress"}
    threading.Thread(target=pipeline.run_pipeline, kwargs={"trigger": "manual"}, daemon=True).start()
    return {"started": True}


class PipelineTrigger(BaseModel):
    enabled: bool = True
    trigger_mode: str = "periodic"
    interval_minutes: int = 120
    folders: str | None = None


def _pipelines() -> list[dict]:
    out = rows("SELECT key, name, description, folders, trigger_mode, enabled, interval_minutes, last_run_at, next_run_at FROM pipeline_config ORDER BY id")
    for p in out:
        with SessionLocal() as s:
            p["files"] = len(pipeline.watched_files(s, p["key"], [x for x in p["folders"].split(",") if x]))
    return out


@router.get("/admin/pipelines")
def pipelines_get():
    return {"pipelines": _pipelines(), "running": pipeline._lock.locked()}


@router.put("/admin/pipelines/{key}")
def pipelines_put(key: str, c: PipelineTrigger):
    if c.trigger_mode not in scheduler.TRIGGERS:
        raise HTTPException(422, f"trigger must be one of {', '.join(scheduler.TRIGGERS)}")
    if not 1 <= c.interval_minutes <= 60 * 24 * 7:
        raise HTTPException(422, "interval must be between 1 minute and 7 days")
    if not rows("SELECT 1 FROM pipeline_config WHERE key=:k", k=key):
        raise HTTPException(404, "unknown pipeline")
    with SessionLocal() as s:
        scheduler.set_interval(s, c.interval_minutes, c.enabled, key, c.trigger_mode, c.folders)
        s.commit()
    return pipelines_get()


class ModeIn(BaseModel):
    demo: bool


@router.put("/admin/mode")
def set_mode(b: ModeIn, request: Request):
    """Demo (no Claude, simulated systems) <-> Live (every module LLM-based)."""
    from app import llm, mode
    from app.routes_auth import me

    mode.set_demo(b.demo, me(request).get("email"))
    return {"demo_mode": b.demo, "engine": llm.provider(), "note": "Stored documents keep the data of the engine that read them. Re-extract to refresh them with the current engine."}


@router.post("/admin/pipelines/{key}/run")
def pipelines_run(key: str, force: bool = False):
    if not rows("SELECT 1 FROM pipeline_config WHERE key=:k", k=key):
        raise HTTPException(404, "unknown pipeline")
    if pipeline._lock.locked():
        return {"started": False, "message": "a run is already in progress"}
    threading.Thread(target=pipeline.run_pipeline, kwargs={"trigger": "manual" if not force else "re-extract", "pipeline_key": key, "force": force}, daemon=True).start()
    return {"started": True}


@router.get("/admin/pipeline/runs")
def pipeline_runs():
    return rows("SELECT * FROM pipeline_runs ORDER BY id DESC LIMIT 25")


@router.get("/admin/pipeline/runs/{rid}/events")
def pipeline_events(rid: int):
    return rows("SELECT id, path, contract_id, action, detail, content_hash, size_bytes, reason, created_at FROM pipeline_events WHERE run_id=:r ORDER BY id", r=rid)


class UploadIn(BaseModel):
    filename: str
    content: str
    category: str | None = None
    owner: str | None = None
    status: str = "active"


@router.post("/admin/pipeline/upload")
def pipeline_upload(u: UploadIn):
    """Drop a document into the inbox and process it straight away."""
    if not u.content.strip():
        raise HTTPException(422, "document is empty")
    p = pipeline.add_document(u.filename, u.content, {"category": u.category, "owner": u.owner, "status": u.status, "origin": "upload"},
                             subdir="drafts" if u.status == "draft" else "uploads")
    res = pipeline.run_pipeline("upload", only=[p])
    return {"saved_as": str(p.name), "run": res}


# ------------------------------------------------------------------ KCC library
class KccIn(BaseModel):
    key: str | None = None
    name: str
    description: str | None = None
    category: str | None = "Key clause"
    keywords: list[str] = []
    heading_aliases: list[str] = []
    standard_text: str | None = None
    playbook_position: str | None = None
    fallback_text: str | None = None
    severity_if_missing: str = "medium"
    applies_to: list[str] = []
    in_matrix: bool = True
    enabled: bool = True


def _clean_list(xs: list[str]) -> list[str]:
    return [x.strip() for x in xs if x and x.strip()]


@router.get("/admin/kcc")
def kcc_list():
    use = {r["clause_type"]: r["n"] for r in rows("SELECT clause_type, count(DISTINCT contract_id) AS n FROM clauses GROUP BY 1")}
    out = rows("SELECT * FROM kcc_library ORDER BY sort_order, key")
    for k in out:
        k["documents"] = use.get(k["key"], 0)
    return out


@router.post("/admin/kcc")
def kcc_create(k: KccIn):
    key = k.key or re.sub(r"[^a-z0-9]+", "_", k.name.lower()).strip("_")
    if not SLUG.match(key):
        raise HTTPException(422, "key must be lowercase letters, digits and underscores")
    if rows("SELECT 1 FROM kcc_library WHERE key=:k", k=key):
        raise HTTPException(409, f"a clause with key '{key}' already exists")
    if k.severity_if_missing not in SEV:
        raise HTTPException(422, "bad severity")
    n = rows("SELECT coalesce(max(sort_order),0)+1 AS n FROM kcc_library")[0]["n"]
    run_sql("""INSERT INTO kcc_library (key,name,description,category,keywords,heading_aliases,standard_text,playbook_position,fallback_text,
                 severity_if_missing,applies_to,in_matrix,enabled,sort_order,builtin)
               VALUES (:key,:name,:d,:cat,:kw,:al,:st,:pb,:fb,:sv,:ap,:im,:en,:so,false)""",
            key=key, name=k.name, d=k.description, cat=k.category, kw=_clean_list(k.keywords),
            al=_clean_list(k.heading_aliases) or [k.name], st=k.standard_text, pb=k.playbook_position, fb=k.fallback_text,
            sv=k.severity_if_missing, ap=k.applies_to, im=k.in_matrix, en=k.enabled, so=n)
    return {"key": key, **_reprocess()}


@router.put("/admin/kcc/{key}")
def kcc_update(key: str, k: KccIn):
    if not rows("SELECT 1 FROM kcc_library WHERE key=:k", k=key):
        raise HTTPException(404, "not found")
    run_sql("""UPDATE kcc_library SET name=:name, description=:d, category=:cat, keywords=:kw, heading_aliases=:al, standard_text=:st,
                 playbook_position=:pb, fallback_text=:fb, severity_if_missing=:sv, applies_to=:ap, in_matrix=:im, enabled=:en WHERE key=:key""",
            key=key, name=k.name, d=k.description, cat=k.category, kw=_clean_list(k.keywords), al=_clean_list(k.heading_aliases) or [k.name],
            st=k.standard_text, pb=k.playbook_position, fb=k.fallback_text, sv=k.severity_if_missing, ap=k.applies_to, im=k.in_matrix, en=k.enabled)
    return {"key": key, **_reprocess()}


@router.delete("/admin/kcc/{key}")
def kcc_delete(key: str):
    r = rows("SELECT builtin FROM kcc_library WHERE key=:k", k=key)
    if not r:
        raise HTTPException(404, "not found")
    if r[0]["builtin"]:
        raise HTTPException(409, "built-in clauses can be disabled, not deleted")
    run_sql("DELETE FROM kcc_library WHERE key=:k", k=key)
    return {"deleted": key, **_reprocess()}


class KccTest(BaseModel):
    keywords: list[str] = []
    heading_aliases: list[str] = []


@router.post("/admin/kcc/test")
def kcc_test(t: KccTest):
    """Preview: which existing clauses would this definition identify? (nothing is saved)"""
    kws = [k for k in _clean_list(t.keywords) if _ok(k)]
    als = {a.lower() for a in _clean_list(t.heading_aliases)}
    hits = []
    for c in rows("""SELECT cl.id, cl.heading, cl.text, cl.page, cl.clause_type, c.title, c.id AS contract_id
                     FROM clauses cl JOIN contracts c ON c.id = cl.contract_id ORDER BY c.id, cl.id"""):
        by_alias = c["heading"].lower() in als
        by_kw = [k for k in kws if re.search(k, c["text"], re.I)]
        if by_alias or by_kw:
            hits.append({**c, "matched_by": "heading" if by_alias else "keyword: " + by_kw[0], "text": c["text"][:240]})
    return {"clauses": len(hits), "documents": len({h["contract_id"] for h in hits}), "examples": hits[:25]}


def _ok(p: str) -> bool:
    try:
        re.compile(p)
        return True
    except re.error:
        return False


# ------------------------------------------------------------------ metrics (values & limits)
class MetricIn(BaseModel):
    key: str | None = None
    name: str
    description: str | None = None
    kcc_key: str | None = None
    pattern: str
    kind: str = "number"
    unit: str | None = None
    scale: float = 1
    enabled: bool = True
    better: str | None = None          # 'higher' | 'lower': which way is good (benchmarks, SLA breach direction)
    sla: bool = False                  # measured monthly from the monitoring feed (SLA tracking)


@router.get("/admin/metrics")
def metrics_list():
    cov = {r["metric_key"]: r["n"] for r in rows("SELECT metric_key, count(*) AS n FROM extracted_values GROUP BY 1")}
    out = rows("SELECT * FROM metrics ORDER BY name")
    for m in out:
        m["documents"] = cov.get(m["key"], 0)
    return out


@router.post("/admin/metrics")
def metric_create(m: MetricIn):
    key = m.key or re.sub(r"[^a-z0-9]+", "_", m.name.lower()).strip("_")
    if not SLUG.match(key):
        raise HTTPException(422, "bad key")
    if not _ok(m.pattern):
        raise HTTPException(422, "the pattern is not a valid regular expression")
    if rows("SELECT 1 FROM metrics WHERE key=:k", k=key):
        raise HTTPException(409, "a metric with that key exists")
    run_sql("INSERT INTO metrics (key,name,description,kcc_key,pattern,kind,unit,scale,enabled,builtin,better,sla) VALUES (:k,:n,:d,:c,:p,:kind,:u,:s,:e,false,:b,:sl)",
            k=key, n=m.name, d=m.description, c=m.kcc_key or None, p=m.pattern, kind=m.kind, u=m.unit, s=m.scale, e=m.enabled, b=m.better or None, sl=m.sla)
    return {"key": key, **_reprocess()}


@router.put("/admin/metrics/{key}")
def metric_update(key: str, m: MetricIn):
    if not _ok(m.pattern):
        raise HTTPException(422, "the pattern is not a valid regular expression")
    run_sql("UPDATE metrics SET name=:n, description=:d, kcc_key=:c, pattern=:p, kind=:kind, unit=:u, scale=:s, enabled=:e, better=:b, sla=:sl WHERE key=:k",
            k=key, n=m.name, d=m.description, c=m.kcc_key or None, p=m.pattern, kind=m.kind, u=m.unit, s=m.scale, e=m.enabled, b=m.better or None, sl=m.sla)
    return {"key": key, **_reprocess()}


@router.delete("/admin/metrics/{key}")
def metric_delete(key: str):
    r = rows("SELECT builtin FROM metrics WHERE key=:k", k=key)
    if not r:
        raise HTTPException(404, "not found")
    if r[0]["builtin"]:
        raise HTTPException(409, "built-in metrics can be disabled, not deleted")
    run_sql("DELETE FROM checklist_rules WHERE metric_key=:k", k=key)
    run_sql("DELETE FROM metrics WHERE key=:k", k=key)
    return {"deleted": key, **_reprocess()}


@router.post("/admin/metrics/test")
def metric_test(m: MetricIn):
    """Preview: what would this extractor pull out of the existing documents?"""
    if not _ok(m.pattern):
        raise HTTPException(422, "the pattern is not a valid regular expression")
    out = []
    for c in rows("""SELECT cl.id, cl.clause_type, cl.text, cl.page, c.title FROM clauses cl JOIN contracts c ON c.id=cl.contract_id
                     WHERE (CAST(:k AS text) IS NULL OR cl.clause_type = :k) ORDER BY c.id, cl.id""", k=m.kcc_key or None):
        found = kcc.extract_metrics([c], [{"key": "x", "kcc_key": m.kcc_key or None, "pattern": m.pattern, "kind": m.kind, "unit": m.unit, "scale": m.scale}])
        if found:
            v = found[0]
            out.append({"title": c["title"], "value": v["value_text"] if v["value_text"] is not None else v["value_num"], "page": c["page"], "excerpt": c["text"][:200]})
    return {"matches": len(out), "examples": out[:25]}


# ------------------------------------------------------------------ checklist rules
class RuleIn(BaseModel):
    key: str | None = None
    name: str
    description: str | None = None
    rule_type: str
    kcc_key: str | None = None
    metric_key: str | None = None
    operator: str | None = None
    threshold: float | None = None
    threshold_text: str | None = None
    phrase: str | None = None
    severity: str = "medium"
    applies_to: list[str] = []
    categories: list[str] = []
    stage: str = "any"
    suggested_text: str | None = None
    enabled: bool = True


def _check_rule(r: RuleIn):
    if r.rule_type not in ("clause_required", "clause_forbidden", "metric_threshold", "text_forbidden"):
        raise HTTPException(422, "unknown rule type")
    if r.severity not in SEV or r.stage not in ("any", "pre_sign", "post_sign"):
        raise HTTPException(422, "bad severity or stage")
    if r.rule_type in ("clause_required", "clause_forbidden") and not r.kcc_key:
        raise HTTPException(422, "choose the clause")
    if r.rule_type == "metric_threshold" and (not r.metric_key or r.operator not in ("<=", ">=", "<", ">", "=")):
        raise HTTPException(422, "choose a value and an operator")
    if r.rule_type == "text_forbidden" and (not r.phrase or not _ok(r.phrase)):
        raise HTTPException(422, "enter a valid phrase / pattern")


@router.get("/admin/rules")
def rules_list():
    stats = {}
    for r in rows("SELECT rule_key, status, count(*) AS n FROM check_results GROUP BY 1,2"):
        stats.setdefault(r["rule_key"], {})[r["status"]] = r["n"]
    out = rows("SELECT * FROM checklist_rules ORDER BY sort_order, key")
    for r in out:
        r["results"] = stats.get(r["key"], {})
        r["threshold"] = float(r["threshold"]) if r["threshold"] is not None else None
    return out


@router.post("/admin/rules")
def rule_create(r: RuleIn):
    _check_rule(r)
    key = r.key or re.sub(r"[^a-z0-9]+", "_", r.name.lower()).strip("_")[:48]
    if not SLUG.match(key):
        raise HTTPException(422, "bad key")
    if rows("SELECT 1 FROM checklist_rules WHERE key=:k", k=key):
        raise HTTPException(409, "a rule with that key exists")
    n = rows("SELECT coalesce(max(sort_order),0)+1 AS n FROM checklist_rules")[0]["n"]
    run_sql("""INSERT INTO checklist_rules (key,name,description,rule_type,kcc_key,metric_key,operator,threshold,threshold_text,phrase,severity,
                 applies_to,categories,stage,suggested_text,enabled,sort_order,builtin)
               VALUES (:k,:n,:d,:t,:kc,:mk,:op,:th,:tt,:ph,:sv,:ap,:cat,:st,:sx,:en,:so,false)""",
            k=key, n=r.name, d=r.description, t=r.rule_type, kc=r.kcc_key, mk=r.metric_key, op=r.operator, th=r.threshold, tt=r.threshold_text,
            ph=r.phrase, sv=r.severity, ap=r.applies_to, cat=r.categories, st=r.stage, sx=r.suggested_text, en=r.enabled, so=n)
    return {"key": key, **_reprocess()}


@router.put("/admin/rules/{key}")
def rule_update(key: str, r: RuleIn):
    _check_rule(r)
    run_sql("""UPDATE checklist_rules SET name=:n, description=:d, rule_type=:t, kcc_key=:kc, metric_key=:mk, operator=:op, threshold=:th,
                 threshold_text=:tt, phrase=:ph, severity=:sv, applies_to=:ap, categories=:cat, stage=:st, suggested_text=:sx, enabled=:en WHERE key=:k""",
            k=key, n=r.name, d=r.description, t=r.rule_type, kc=r.kcc_key, mk=r.metric_key, op=r.operator, th=r.threshold, tt=r.threshold_text,
            ph=r.phrase, sv=r.severity, ap=r.applies_to, cat=r.categories, st=r.stage, sx=r.suggested_text, en=r.enabled)
    return {"key": key, **_reprocess()}


@router.delete("/admin/rules/{key}")
def rule_delete(key: str):
    r = rows("SELECT builtin FROM checklist_rules WHERE key=:k", k=key)
    if not r:
        raise HTTPException(404, "not found")
    if r[0]["builtin"]:
        raise HTTPException(409, "built-in rules can be disabled, not deleted")
    run_sql("DELETE FROM checklist_rules WHERE key=:k", k=key)
    return {"deleted": key, **_reprocess()}


# ------------------------------------------------------------------ new contract
class GenIn(BaseModel):
    template: str = ""
    params: dict = {}
    md: str | None = None


@router.get("/generator/forms")
def gen_forms():
    return {"forms": generator.forms(), "vendors": [r["vendor"] for r in rows("SELECT DISTINCT vendor FROM contracts WHERE status<>'draft' ORDER BY 1")],
            "parents": rows("SELECT id, title, type, vendor FROM contracts WHERE status<>'draft' AND type IN ('MSA','SOW','SaaS') ORDER BY vendor, title")}


class BriefIn(BaseModel):
    text: str | None = None
    filename: str | None = None
    content_b64: str | None = None
    template: str | None = None


@router.post("/generator/brief")
def gen_brief(b: BriefIn):
    """Read deal details given as text or an uploaded file and return the form values found."""
    import base64

    from app import brief, ingest_text

    try:
        txt = b.text if b.text else ingest_text.extract_text(b.filename or "brief.txt", base64.b64decode(b.content_b64 or ""))
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not txt.strip():
        raise HTTPException(422, "nothing to read: paste some details or choose a file")
    return brief.read_brief(txt, b.template)


@router.get("/generator/library")
def gen_library():
    return generator.clause_library()


@router.post("/generator/preview")
def gen_preview(g: GenIn):
    try:
        b = generator.build(g.template, g.params)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))
    return {"title": b["title"], "md": b["md"], "analysis": generator.dry_run(b["md"])}


@router.post("/generator/analyze")
def gen_analyze(g: GenIn):
    return generator.dry_run(g.md or "")


@router.post("/generator/create")
def gen_create(g: GenIn):
    try:
        return generator.create(g.template, g.params, g.md)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, str(e))


# ------------------------------------------------------------------ thresholds (config_items) and obligation rules
@router.get("/admin/config")
def config_get():
    out: dict[str, list] = {}
    for r in rows("SELECT grp, key, label, description, value, kind FROM config_items ORDER BY grp, sort_order, key"):
        out.setdefault(r["grp"], []).append(r)
    return {"groups": out, "titles": {"spend": "Spend checks", "risk": "Vendor risk: tiers and saturation", "risk_points": "Vendor risk: points per finding", "sla": "SLA"}}


class ConfigIn(BaseModel):
    value: float | int | list | str | bool | None


@router.put("/admin/config/{grp}/{key}")
def config_put(grp: str, key: str, b: ConfigIn):
    import json

    r = rows("SELECT kind FROM config_items WHERE grp=:g AND key=:k", g=grp, k=key)
    if not r:
        raise HTTPException(404, "unknown setting")
    if r[0]["kind"] == "number" and not isinstance(b.value, (int, float)):
        raise HTTPException(422, "this setting is a number")
    if r[0]["kind"] == "json" and not isinstance(b.value, list):
        raise HTTPException(422, "this setting is a list")
    run_sql("UPDATE config_items SET value=CAST(:v AS jsonb) WHERE grp=:g AND key=:k", v=json.dumps(b.value), g=grp, k=key)
    from app import feeds

    return {"saved": True, **feeds.recompute()}


class ObligationRuleIn(BaseModel):
    key: str | None = None
    name: str
    metric_key: str | None = None
    kind: str
    party: str = "Supplier"
    title_template: str
    frequency: str = "event"
    unit: str | None = None
    annual: bool = False
    enabled: bool = True


@router.get("/admin/obligation-rules")
def obl_rules():
    return {"rules": rows("""SELECT r.*, (SELECT count(*) FROM obligations o WHERE o.key = 'metric:' || r.metric_key) AS obligations FROM obligation_rules r ORDER BY sort_order, key"""),
            "metrics": rows("SELECT key, name, unit FROM metrics WHERE enabled ORDER BY name")}


def _check_obl_rule(b: ObligationRuleIn) -> None:
    if b.party not in ("Supplier", "Customer", "Both") or b.frequency not in ("once", "monthly", "quarterly", "annual", "event"):
        raise HTTPException(422, "party must be Supplier, Customer or Both; frequency once, monthly, quarterly, annual or event")
    try:
        b.title_template.format(v=1.0)
    except (KeyError, IndexError, ValueError):
        raise HTTPException(422, "the title may use only {v}, e.g. 'Pay within {v:g} days'")
    if b.metric_key and not rows("SELECT 1 FROM metrics WHERE key=:k", k=b.metric_key):
        raise HTTPException(422, "unknown metric")


@router.post("/admin/obligation-rules")
def obl_rule_create(b: ObligationRuleIn):
    _check_obl_rule(b)
    key = b.key or re.sub(r"[^a-z0-9]+", "_", b.name.lower()).strip("_")
    if rows("SELECT 1 FROM obligation_rules WHERE key=:k", k=key):
        raise HTTPException(409, "a rule with that key exists")
    run_sql("INSERT INTO obligation_rules (key,name,metric_key,kind,party,title_template,frequency,unit,annual,enabled,builtin,sort_order) VALUES (:k,:n,:m,:kd,:p,:t,:f,:u,:a,:e,false,999)",
            k=key, n=b.name, m=b.metric_key, kd=b.kind, p=b.party, t=b.title_template, f=b.frequency, u=b.unit, a=b.annual, e=b.enabled)
    return {"key": key, **_reprocess()}


@router.put("/admin/obligation-rules/{key}")
def obl_rule_update(key: str, b: ObligationRuleIn):
    _check_obl_rule(b)
    run_sql("UPDATE obligation_rules SET name=:n, metric_key=:m, kind=:kd, party=:p, title_template=:t, frequency=:f, unit=:u, annual=:a, enabled=:e WHERE key=:k",
            k=key, n=b.name, m=b.metric_key, kd=b.kind, p=b.party, t=b.title_template, f=b.frequency, u=b.unit, a=b.annual, e=b.enabled)
    return {"key": key, **_reprocess()}


@router.delete("/admin/obligation-rules/{key}")
def obl_rule_delete(key: str):
    r = rows("SELECT builtin FROM obligation_rules WHERE key=:k", k=key)
    if not r:
        raise HTTPException(404, "not found")
    if r[0]["builtin"]:
        raise HTTPException(409, "built-in rules can be disabled, not deleted")
    run_sql("DELETE FROM obligation_rules WHERE key=:k", k=key)
    return {"deleted": key, **_reprocess()}
