"""Document pipeline: pick up new or changed documents from the inbox folder and turn them into data.

For every document: parse -> classify clauses (KCC library) -> extract fields (Claude, or the
offline extractor) -> embed -> extract values & limits -> compare to the standard template ->
run the redline checklist. Everything lands in the same tables that every screen and the Ask
assistant read, so all modules see one unified dataset. Idempotent: a file is re-processed only when
its content hash changes."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import deviations, docstruct, embeddings, extraction, kcc, llm, meta_rules, obligations
from app.config import data_path
from app.db import SessionLocal
from app.docgen.generate import render_template
from app.docgen.library import TEMPLATES
from app.models import Clause, ClauseDeviation, Contract, FieldExtraction, Template, TemplateClause
from app.parsing import parse_document

SUPPORTED = {".md", ".txt", ".docx", ".pdf", ".html", ".htm"}
OVERRIDABLE = {"expiry_date", "notice_period_days", "auto_renew", "annual_value", "total_value", "payment_terms_days",
               "liability_cap_multiple", "liability_cap_text", "termination_for_convenience", "governing_law"}
DATE_FIELDS = {"effective_date", "expiry_date", "customer_signed_date", "supplier_signed_date"}
TEMPLATE_KEY = {"MSA": "MSA", "SOW": "SOW", "Work Order": "WO", "NDA": "NDA", "SaaS": "SaaS", "DPA": "DPA", "Amendment": "MSA"}
TYPE_GUESS = [(r"master services|master agreement|\bmsa\b", "MSA"), (r"statement of work|\bsow\b", "SOW"), (r"work order", "Work Order"),
              (r"non-disclosure|confidentiality agreement|\bnda\b", "NDA"), (r"data processing", "DPA"),
              (r"subscription|saas|software as a service|license and support", "SaaS"), (r"amendment", "Amendment")]
_lock = threading.Lock()


def inbox_path(s=None) -> Path:
    if s is not None:
        p = s.execute(text("SELECT inbox_path FROM pipeline_config WHERE id = 1")).scalar()
        if p:
            return Path(p)
    return data_path() / "inbox"


def _coerce(field: str, v):
    if v is None:
        return None
    return date.fromisoformat(v) if field in DATE_FIELDS else v


EDITABLE = {"effective_date": "date", "expiry_date": "date", "customer_signed_date": "date", "supplier_signed_date": "date", "notice_period_days": "int", "payment_terms_days": "int",
            "annual_value": "num", "total_value": "num", "liability_cap_multiple": "num", "auto_renew": "bool", "termination_for_convenience": "bool", "processes_personal_data": "bool",
            "has_dpa": "bool", "fully_executed": "bool", "governing_law": "text", "liability_cap_text": "text", "customer_signatory": "text", "supplier_signatory": "text"}


def coerce_input(field: str, raw):
    """A typed value from what a person entered or what was stored: '' / None means 'not stated'. Raises ValueError for a value that does not fit the field."""
    kind = EDITABLE.get(field)
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    if kind == "date":
        return raw if isinstance(raw, date) else date.fromisoformat(str(raw).strip())
    if kind == "int":
        return int(float(raw))
    if kind == "num":
        return float(str(raw).replace(",", "").replace("$", ""))
    if kind == "bool":
        if isinstance(raw, bool):
            return raw
        v = str(raw).strip().lower()
        if v in ("true", "yes", "y", "1"):
            return True
        if v in ("false", "no", "n", "0"):
            return False
        raise ValueError("expected yes or no")
    return str(raw).strip()


def infer_metadata(md: str, header: dict, clauses: list[dict], sidecar: dict, folder_hint: str = "") -> dict:
    """Vendor / type / title / parent come from the document itself (rules for real contracts); category, owner, status from an optional sidecar or the folder."""
    if not header.get("Parties") and not header.get("Document Type"):
        m = meta_rules.infer(md, header, clauses, sidecar, folder_hint)
        return dict(title=m["title"], vendor=m["vendor"], type=m["type"], category=m["category"], owner=m["owner"], status=m["status"],
                    parent_title=sidecar.get("parent_title"), parent_ref=m["parent_ref"], template_key=TEMPLATE_KEY[m["type"]])
    title = next((ln[2:].strip() for ln in md.splitlines() if ln.startswith("# ")), "Untitled document")
    parties = header.get("Parties", "")
    m = re.search(r'and (.+?) \(the "Supplier"\)', parties)
    vendor = m.group(1).strip() if m else sidecar.get("vendor") or "Unknown vendor"
    doc_type = header.get("Document Type", "").strip()
    if doc_type not in TEMPLATE_KEY:
        hay = f"{title} {doc_type}".lower()
        doc_type = next((t for rx, t in TYPE_GUESS if re.search(rx, hay)), "MSA")
    if header.get("Amends"):
        doc_type = "Amendment"
    parent = sidecar.get("parent_title") or header.get("Amends")
    by = {c["clause_type"]: c for c in clauses}
    if not parent:
        if "msa_reference" in by and (mm := re.search(r"\((.+?)\)\. Capitalised", by["msa_reference"]["text"])):
            parent = mm.group(1)
        elif "sow_reference" in by and (mm := re.search(r"issued under (.+?) \(effective", by["sow_reference"]["text"])):
            parent = mm.group(1)
        elif doc_type == "DPA" and (mm := re.search(r"supplements the (.+?) and applies", " ".join(c["text"] for c in clauses))):
            parent = mm.group(1)
    return dict(title=title, vendor=vendor, type=doc_type, category=sidecar.get("category") or "Uncategorised",
                owner=sidecar.get("owner") or "Unassigned", status=sidecar.get("status") or "active",
                parent_title=parent, parent_ref=None, template_key=TEMPLATE_KEY[doc_type])


# ------------------------------------------------------------------ templates
def ensure_templates(s, root: Path | None = None) -> dict[str, int]:
    """Load the standard templates once. Returns {template type: id}."""
    have = {r[0]: r[1] for r in s.execute(text("SELECT type, id FROM templates"))}
    for tt, t in TEMPLATES.items():
        if tt in have:
            continue
        md, meta = render_template(tt)
        row = Template(name=f"{t['name']} (Standard)", type=tt, version="1.0", body_md=md)
        s.add(row)
        s.flush()
        have[tt] = row.id
        for m in meta:
            s.add(TemplateClause(template_id=row.id, **m))
    s.flush()
    return have


# ------------------------------------------------------------------ one document
def _clear_derived(s, cid: int) -> None:
    for t in ("clause_deviations", "field_extractions", "extracted_values", "check_results", "redlines"):
        s.execute(text(f"DELETE FROM {t} WHERE contract_id = :c"), {"c": cid})
    s.execute(text("DELETE FROM clauses WHERE contract_id = :c"), {"c": cid})


def derive(s, contract: Contract, clauses_db: list[dict], cfg: dict, template_key: str, mode: str) -> dict:
    """Values/limits, deviations and checklist for one document, from its stored clauses."""
    cid = contract.id
    s.execute(text("DELETE FROM extracted_values WHERE contract_id=:c"), {"c": cid})
    s.execute(text("DELETE FROM check_results WHERE contract_id=:c"), {"c": cid})
    s.execute(text("DELETE FROM clause_deviations WHERE contract_id=:c"), {"c": cid})
    s.execute(text("DELETE FROM redlines WHERE contract_id=:c"), {"c": cid})
    vals = kcc.extract_metrics(clauses_db, cfg["metrics"], cfg["kcc"])
    for v in vals:
        s.execute(text("INSERT INTO extracted_values (contract_id, metric_key, value_num, value_text, clause_id, page, confidence) "
                       "VALUES (:c,:k,:n,:t,:cl,:p,:cf)"),
                  {"c": cid, "k": v["metric_key"], "n": v["value_num"], "t": v["value_text"], "cl": v["clause_id"], "p": v["page"], "cf": v["confidence"]})
    results = kcc.evaluate_rules(contract.type, contract.status, clauses_db, vals, cfg["metrics"], cfg["rules"], bool(contract.fully_executed))
    for r in results:
        s.execute(text("INSERT INTO check_results (contract_id, rule_key, status, actual, expected, severity, clause_id, page, excerpt) "
                       "VALUES (:c,:k,:st,:a,:e,:sv,:cl,:p,:x)"),
                  {"c": cid, "k": r["rule_key"], "st": r["status"], "a": r["actual"], "e": r["expected"], "sv": r["severity"],
                   "cl": r["clause_id"], "p": r["page"], "x": r["excerpt"]})
    items = []
    if contract.type != "Amendment":
        from app.config import settings

        scope = settings.redline_llm_scope
        use = mode if (scope == "all" or (scope == "drafts" and contract.status == "draft")) else "heuristic"
        items = deviations.compare_document(clauses_db, template_key, use)
        for it in items:
            tcid = cfg["tclause"].get((template_key, it["clause_type"]))
            if tcid:
                s.add(ClauseDeviation(contract_id=cid, template_clause_id=tcid, deviation_summary=it["deviation"], severity=it["severity"]))
    s.execute(text("INSERT INTO redlines (contract_id, items) VALUES (:c, CAST(:i AS jsonb))"), {"c": cid, "i": json.dumps(items)})
    n_obl = obligations.derive(s, contract, clauses_db, vals)
    return {"values": len(vals), "checks": len(results), "deviations": len(items), "obligations": n_obl}


def ingest_file(s, path: Path, root: Path, cfg: dict, extractor: str = "auto", redline_mode: str = "auto") -> dict:
    raw = path.read_bytes()
    chash = hashlib.sha256(raw).hexdigest()
    rel = str(path.relative_to(root))
    existing = s.query(Contract).filter(Contract.source_path == rel).first()
    if existing and existing.content_hash == chash:
        return {"action": "unchanged", "contract_id": existing.id, "path": rel}
    md = docstruct.load_document(path)
    sc = path.with_suffix(".meta.json")
    sidecar = json.loads(sc.read_text()) if sc.exists() else {}
    classify = lambda h, t: kcc.classify(h, t, cfg["kcc"])  # noqa: E731
    header, clauses = parse_document(md, classify)
    clauses += kcc.detect_in_text(clauses, md, {c["clause_type"] for c in clauses}, {k["key"] for k in cfg["kcc"] if k.get("enabled", True)},
                                  _custom_keywords(cfg))     # clauses added in Admin are found by sentence too
    meta = infer_metadata(md, header, clauses, sidecar, rel)
    fields, mode = extraction.extract(md, header, clauses, meta["type"], extractor)
    corrections = {r[0]: r[1] for r in s.execute(text("SELECT field, corrected_value FROM field_corrections WHERE source_path=:p"), {"p": rel})}
    for f, v in corrections.items():                 # a person's correction survives re-extraction
        fields[f] = {**fields.get(f, {"clause_type": None, "page": 1}), "value": coerce_input(f, v), "confidence": 1.0, "corrected": True}
    val = {f: _coerce(f, d["value"]) for f, d in fields.items()}
    if meta["type"] in ("DPA", "NDA"):          # a DPA is not 'covered by a DPA'; an NDA processes no personal data: same result in every engine
        val["has_dpa"] = False
        if meta["type"] == "NDA":
            val["processes_personal_data"] = False
    tid = cfg["templates"].get(meta["template_key"])
    attrs = dict(
        title=meta["title"], vendor=meta["vendor"], category=meta["category"], type=meta["type"], template_id=tid,
        status=meta["status"], owner=meta["owner"], body_md=md, currency="USD", source_path=rel, content_hash=chash,
        ingested_at=datetime.now(timezone.utc), origin=sidecar.get("origin", "inbox"), source_url=sidecar.get("source_url"),
        overrides=sorted(set(val) & OVERRIDABLE) if meta["type"] == "Amendment" else [],
        effective_date=val.get("effective_date"), expiry_date=val.get("expiry_date"), notice_period_days=val.get("notice_period_days"),
        auto_renew=bool(val.get("auto_renew")), annual_value=val.get("annual_value"), total_value=val.get("total_value"),
        payment_terms_days=val.get("payment_terms_days"), liability_cap_multiple=val.get("liability_cap_multiple"),
        liability_cap_text=val.get("liability_cap_text"), termination_for_convenience=val.get("termination_for_convenience"),
        governing_law=val.get("governing_law"), processes_personal_data=bool(val.get("processes_personal_data")),
        has_dpa=bool(val.get("has_dpa")), customer_signatory=val.get("customer_signatory"),
        customer_signed_date=val.get("customer_signed_date"), supplier_signatory=val.get("supplier_signatory"),
        supplier_signed_date=val.get("supplier_signed_date"), fully_executed=bool(val.get("fully_executed")),
    )
    if existing:
        _clear_derived(s, existing.id)
        for k, v in attrs.items():
            setattr(existing, k, v)
        contract, action = existing, "updated"
    else:
        contract = Contract(**attrs)
        s.add(contract)
        action = "new"
    s.flush()
    vecs = embeddings.embed([f"{c['heading']}. {c['text']}" for c in clauses]) if clauses else []
    by_type, db_clauses = {}, []
    for c, v in zip(clauses, vecs):
        row = Clause(contract_id=contract.id, clause_type=c["clause_type"], heading=c["heading"], text=c["text"], page=c["page"], embedding=v)
        s.add(row)
        s.flush()
        by_type.setdefault(c["clause_type"], row.id)
        db_clauses.append({"id": row.id, "clause_type": c["clause_type"], "heading": c["heading"], "text": c["text"], "page": c["page"]})
    for f, d in fields.items():
        s.add(FieldExtraction(contract_id=contract.id, field=f, value=None if d["value"] is None else str(d["value"]), corrected=bool(d.get("corrected")),
                              confidence=d["confidence"], source_clause_id=by_type.get(d["clause_type"]), source_page=d["page"]))
    stats = derive(s, contract, db_clauses, cfg, meta["template_key"], redline_mode if redline_mode != "auto" else "auto")
    return {"action": action, "contract_id": contract.id, "path": rel, "title": meta["title"], "parent_title": meta["parent_title"] or meta.get("parent_ref"),
            "extractor": mode, **stats}


def link_parents(s, pending: dict) -> int:
    """Resolve parent_id from what each document says about its parent (an exact title, or type + date + number), then from the usual
    hierarchy for the same vendor. Works whatever order the files arrived in."""
    n = 0
    for cid, ref in pending.items():
        pid = meta_rules.resolve_parent(s, cid, ref)
        if pid:
            s.execute(text("UPDATE contracts SET parent_id=:p WHERE id=:i"), {"p": pid, "i": cid})
            n += 1
    return n


def load_config(s) -> dict:
    tmpl = ensure_templates(s)
    tclause = {(r[0], r[1]): r[2] for r in s.execute(text(
        "SELECT t.type, tc.clause_type, tc.id FROM template_clauses tc JOIN templates t ON t.id = tc.template_id"))}
    return dict(kcc=kcc.load_kcc(s), metrics=kcc.load_metrics(s), rules=kcc.load_rules(s), templates=tmpl, tclause=tclause)


def scan(root: Path, folders: list[str] | None = None) -> list[Path]:
    """Supported files under the inbox; with `folders`, only those sub-folders (a pipeline's watch list)."""
    bases = [root / f for f in folders] if folders else [root]
    return sorted(p for b in bases if b.exists() for p in b.rglob("*")
                  if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.endswith(".meta.json")
                  and not any(part.startswith(("_", ".")) for part in p.relative_to(root).parts))


def watched_files(s, key: str, folders: list[str]) -> list[Path]:
    """Files a pipeline watches: the inbox sub-folders, or (feeds) the CSV files in data/feeds."""
    if key == "feeds":
        from app import feeds

        d = feeds.feeds_dir()
        return feeds.feed_files() if d.exists() else []
    return scan(inbox_path(s), folders)


def fingerprint(files: list[Path]) -> str:
    """Cheap change detector for a folder: names, sizes and modification times."""
    import hashlib

    h = hashlib.sha1()
    for f in files:
        st = f.stat()
        h.update(f"{f.name}|{st.st_size}|{st.st_mtime_ns}".encode())
    return h.hexdigest()


def pipeline_folders(s, key: str) -> list[str]:
    raw = s.execute(text("SELECT folders FROM pipeline_config WHERE key=:k"), {"k": key}).scalar() or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


# ------------------------------------------------------------------ a run
def run_pipeline(trigger: str = "manual", extractor: str = "auto", only: list[Path] | None = None, log=lambda *_: None,
                 pipeline_key: str | None = None) -> dict:
    """Process the inbox (or one pipeline's folders, or only the given files). Safe to call from the scheduler, the API and the seed."""
    if pipeline_key == "feeds":
        from app import feeds

        return feeds.run_feeds(trigger)
    if not _lock.acquire(blocking=False):
        return {"status": "busy", "message": "a pipeline run is already in progress"}
    t0 = time.time()
    run_id = None
    try:
        with SessionLocal() as s:
            kcc.ensure_defaults(s)
            root = inbox_path(s)
            root.mkdir(parents=True, exist_ok=True)
            folders = pipeline_folders(s, pipeline_key) if pipeline_key else None
            run_id = s.execute(text("INSERT INTO pipeline_runs (trigger, pipeline) VALUES (:t, :p) RETURNING id"), {"t": trigger, "p": pipeline_key or "all"}).scalar()
            s.commit()
            cfg = load_config(s)
            s.commit()
        files = only if only is not None else scan(root, folders)
        counts = dict(scanned=len(files), new_docs=0, updated=0, unchanged=0, failed=0)
        pending: dict[int, str | None] = {}
        lk = threading.Lock()

        def work(f: Path) -> None:
            try:
                with SessionLocal() as s:
                    r = ingest_file(s, f, root, cfg, extractor)
                    if r["action"] in ("new", "updated"):
                        with lk:
                            pending[r["contract_id"]] = r.get("parent_title")
                    s.execute(text("INSERT INTO pipeline_events (run_id, path, contract_id, action, detail) VALUES (:r,:p,:c,:a,:d)"),
                              {"r": run_id, "p": r["path"], "c": r["contract_id"], "a": r["action"],
                               "d": (f"{r.get('title', '')} · {r.get('values', 0)} values, {r.get('checks', 0)} checks, "
                                     f"{r.get('deviations', 0)} deviations") if r["action"] != "unchanged" else "content unchanged"})
                    s.commit()
                with lk:
                    counts[{"new": "new_docs", "updated": "updated", "unchanged": "unchanged"}[r["action"]]] += 1
            except Exception as e:  # one bad document must not stop the run
                with lk:
                    counts["failed"] += 1
                with SessionLocal() as s:
                    s.execute(text("INSERT INTO pipeline_events (run_id, path, action, detail) VALUES (:r,:p,'failed',:d)"),
                              {"r": run_id, "p": str(f.name), "d": f"{type(e).__name__}: {e}"[:300]})
                    s.commit()

        workers = 4 if llm.available() and extractor != "offline" and len(files) > 1 else 1     # LLM calls dominate: overlap them
        if workers > 1:
            with ThreadPoolExecutor(workers) as ex:
                list(ex.map(work, files))
        else:
            for f in files:
                work(f)
        with SessionLocal() as s:
            linked = link_parents(s, pending)
            s.execute(text("""UPDATE contracts c SET has_dpa = true WHERE c.type <> 'DPA' AND c.status <> 'draft' AND COALESCE(c.has_dpa, false) = false
                              AND EXISTS (SELECT 1 FROM contracts d WHERE d.type = 'DPA' AND d.status <> 'draft' AND d.vendor = c.vendor)"""))
            now = datetime.now(timezone.utc)
            s.execute(text("UPDATE pipeline_runs SET finished_at=now(), status=:st, scanned=:a, new_docs=:b, updated=:c, unchanged=:d, failed=:e, message=:m WHERE id=:i"),
                      {"st": "failed" if counts["failed"] and not (counts["new_docs"] + counts["updated"]) else "completed",
                       "a": counts["scanned"], "b": counts["new_docs"], "c": counts["updated"], "d": counts["unchanged"], "e": counts["failed"],
                       "m": f"linked {linked} parent relationships", "i": run_id})
            if only is None:   # stamp the pipeline(s) that just ran, and remember what the folder looked like
                for k, fl in [(r[0], r[1]) for r in s.execute(text("SELECT key, folders FROM pipeline_config"))]:
                    if (pipeline_key and k != pipeline_key) or k == "feeds":
                        continue
                    fp = fingerprint(scan(root, [x for x in fl.split(",") if x]))
                    s.execute(text("UPDATE pipeline_config SET last_run_at=:n, next_run_at=:n + make_interval(mins => interval_minutes), last_fingerprint=:f WHERE key=:k"),
                              {"n": now, "k": k, "f": fp})
            if trigger == "watch" and not (counts["new_docs"] or counts["updated"] or counts["failed"]):
                s.execute(text("DELETE FROM pipeline_runs WHERE id=:i"), {"i": run_id})   # nothing changed: keep the history quiet
            s.commit()
        try:    # contracts changed: refresh spend exceptions and vendor risk scores
            from app import feeds

            feeds.recompute()
        except Exception:
            pass
        out = {"status": "completed", "run_id": run_id, "seconds": round(time.time() - t0, 2), **counts}
        log(out)
        return out
    finally:
        _lock.release()


def _custom_keywords(cfg: dict) -> dict[str, list[str]]:
    """Clauses an admin added (not built-in): they are also found by sentence, wherever they sit in a document."""
    return {k["key"]: list(k["keywords"]) for k in cfg["kcc"] if not k.get("builtin") and k["key"] not in kcc.PRESENCE and k.get("keywords") and k.get("enabled", True)}


def reprocess_all(extractor: str = "auto") -> dict:
    """After admin edits to the KCC / metrics / checklist: re-classify stored clauses and recompute
    values, deviations and checks for every document (no files are re-read)."""
    with SessionLocal() as s:
        kcc.rebuild_key_clauses_view(s)
        cfg = load_config(s)
        n = 0
        for c in s.query(Contract).all():
            rows = s.execute(text("SELECT id, heading, text, page FROM clauses WHERE contract_id=:c ORDER BY id"), {"c": c.id}).mappings().all()
            db = []
            for r in rows:
                if str(r["heading"]).endswith("(found in text)"):      # synthetic rows are rebuilt below
                    s.execute(text("DELETE FROM clauses WHERE id=:i"), {"i": r["id"]})
                    continue
                t = kcc.classify(r["heading"], r["text"], cfg["kcc"])
                s.execute(text("UPDATE clauses SET clause_type=:t WHERE id=:i"), {"t": t, "i": r["id"]})
                db.append({"id": r["id"], "clause_type": t, "heading": r["heading"], "text": r["text"], "page": r["page"]})
            extra = _custom_keywords(cfg)
            found = kcc.detect_in_text(db, c.body_md or "", {d["clause_type"] for d in db},
                                       {k["key"] for k in cfg["kcc"] if k.get("enabled", True)}, extra)
            if found:
                vecs = embeddings.embed([f"{f['heading']}. {f['text']}" for f in found])
                for f, v in zip(found, vecs):
                    row = Clause(contract_id=c.id, clause_type=f["clause_type"], heading=f["heading"], text=f["text"], page=f["page"], embedding=v)
                    s.add(row)
                    s.flush()
                    db.append({"id": row.id, "clause_type": f["clause_type"], "heading": f["heading"], "text": f["text"], "page": f["page"]})
            derive(s, c, db, cfg, TEMPLATE_KEY.get(c.type, "MSA"), "auto")
            n += 1
        s.commit()
    try:
        from app import feeds

        feeds.recompute()
    except Exception:
        pass
    return {"reprocessed": n}


def add_document(filename: str, content: str, sidecar: dict | None = None, subdir: str = "uploads") -> Path:
    """Drop a document into the inbox (used by the Admin upload and the New Contract page)."""
    with SessionLocal() as s:
        root = inbox_path(s)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename) or "document.md"
    if Path(safe).suffix.lower() not in SUPPORTED:
        safe += ".md"
    d = root / subdir
    d.mkdir(parents=True, exist_ok=True)
    p = d / safe
    p.write_text(content)
    if sidecar:
        p.with_suffix(".meta.json").write_text(json.dumps(sidecar))
    return p
