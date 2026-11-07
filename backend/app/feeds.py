"""Operational feeds: invoices (ERP / AP export), SLA measurements (monitoring / ITSM export) and obligation status updates.
Real feeds are the customer's own files dropped in data/feeds/ (or synced by a connector): CSV exports, or the documents themselves (invoices, monthly
service-level reports, milestone acceptance certificates; PDF / Word / Markdown / scans), read by app.opsdocs and loaded by the 'feeds' pipeline.
`generate_rows()` only exists to make fictional fixtures for demos and tests (see app.docgen.ops_fixtures, which writes them as documents): no screen reads its output directly."""
from __future__ import annotations

import csv
import hashlib
import io
import random
import re
import time
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import text

from app import risk, spend
from app.config import data_path
from app.db import SessionLocal

INVOICE_COLS = ["external_id", "vendor", "contract_title", "invoice_no", "invoice_date", "period_start", "period_end", "due_date", "paid_date", "amount", "description", "category"]
SLA_COLS = ["contract_title", "metric_key", "period", "actual", "incidents", "note"]
STATUS_COLS = ["contract_title", "key", "status", "completed_on", "note"]


def feeds_dir() -> Path:
    return data_path() / "feeds"


def feed_files() -> list[Path]:
    """Everything the feeds pipeline reads: CSV exports and operational documents (invoices, service-level reports, acceptance certificates), in any sub-folder."""
    from app.opsdocs import DOC_EXT

    d = feeds_dir()
    return sorted(f for f in d.rglob("*") if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in DOC_EXT | {".csv"})


FEED_OF = {"invoice": "invoices", "sla_report": "sla", "acceptance": "obligation_status"}


def _read_document(f: Path) -> tuple[str, list[dict]]:
    """Parse one operational document, remembering the result by content hash (OCR and Claude are slow; the same file is not read twice)."""
    import json

    from app import llm, opsdocs

    cache = data_path() / ".cache" / "opsdocs"
    key = hashlib.sha256(f.read_bytes() + opsdocs.PARSER_VERSION.encode() + (b"llm" if llm.available() else b"rules")).hexdigest()
    c = cache / f"{key}.json"
    if c.exists():
        kind, rows = json.loads(c.read_text())
        return kind, rows
    kind, rows = opsdocs.read(f)
    cache.mkdir(parents=True, exist_ok=True)
    c.write_text(json.dumps([kind, rows], default=str))
    return kind, rows


def _add_months(d: date, n: int) -> date:
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    for day in (d.day, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


# ------------------------------------------------------------------ fixture generator (TEST / DEMO DATA ONLY: used to write fictional invoice and report *documents*)
def generate_rows(today: date | None = None, seed: int = 11) -> tuple[list[dict], list[dict], list[dict]]:
    today = today or date.today()
    rnd = random.Random(seed)
    with SessionLocal() as s:
        cons = [dict(r) for r in s.execute(text(
            "SELECT t.contract_id, t.title, t.vendor, t.type, t.category, t.effective_date, t.expiry_date, t.annual_value, t.total_value, t.payment_terms_days "
            "FROM v_effective_terms t WHERE t.status <> 'draft' ORDER BY t.contract_id")).mappings()]
        sla_t = {(r[0], r[1]): float(r[2]) for r in s.execute(text("SELECT contract_id, metric_key, value_num FROM extracted_values WHERE metric_key IN ('sla_availability_pct','incident_notice_hours')"))}
        ms = [dict(r) for r in s.execute(text("SELECT o.contract_id, c.title, c.vendor, o.key, o.due_date FROM obligations o JOIN contracts c ON c.id=o.contract_id WHERE o.kind='milestone' ORDER BY o.contract_id, o.due_date")).mappings()]
    invoices, n = [], 0

    def inv(c, d, amt, desc, ps=None, pe=None, paid_extra=0, vendor=None, title=None, force_unpaid=False, no=None):
        nonlocal n
        n += 1
        terms = int(c["payment_terms_days"] or 45) if c else 45
        due = d + timedelta(days=terms)
        paid = None if force_unpaid or d > today - timedelta(days=terms - 10) else due + timedelta(days=rnd.randint(-6, 2) + paid_extra)
        if paid and paid > today:
            paid = None
        invoices.append(dict(external_id=f"INV-{n:05d}", vendor=vendor or c["vendor"], contract_title=title or (c["title"] if c else ""), invoice_no=no or f"{(vendor or c['vendor'])[:3].upper()}-{d:%y%m}-{n:03d}",
                             invoice_date=d, period_start=ps or "", period_end=pe or "", due_date=due, paid_date=paid or "", amount=round(amt, 2), description=desc, category=(c or {}).get("category") or "IT Services"))

    for c in cons:
        eff, exp, ann, tot = c["effective_date"], c["expiry_date"], c["annual_value"], c["total_value"]
        if not eff or c["type"] in ("MSA", "NDA", "DPA", "Amendment"):
            continue
        if c["type"] == "SaaS" and ann:
            step = 3 if c["contract_id"] % 3 == 0 else 12            # billed quarterly or annually
            k = 0
            while _add_months(eff, k) <= today and _add_months(eff, k) < exp:
                d = _add_months(eff, k)
                inv(c, d, float(ann) * step / 12, f"Subscription {d:%b %Y} – {_add_months(d, step):%b %Y}", d, _add_months(d, step) - timedelta(days=1))
                k += step
        elif c["type"] == "SOW" and ann:
            k = 0
            while _add_months(eff, k + 1) + timedelta(days=5) <= today and _add_months(eff, k + 1) <= exp:
                ps, pe = _add_months(eff, k), _add_months(eff, k + 1) - timedelta(days=1)
                inv(c, pe + timedelta(days=5), float(ann) / 12, f"Services {ps:%d %b} – {pe:%d %b %Y}", ps, pe)
                k += 1
        elif c["type"] == "Work Order" and tot:
            term = (exp - eff).days
            for frac, pct in ((0.25, 0.30), (0.60, 0.40), (1.0, 0.30)):
                d = eff + timedelta(days=int(term * frac))
                if d <= today:
                    inv(c, d, float(tot) * pct, f"Milestone invoice ({int(pct * 100)}% of fixed fee)")
    # ---- demo problems: chosen by RULES over whatever contracts are loaded (no titles or vendors are hardcoded)
    with SessionLocal() as s:
        draft_only = [r[0] for r in s.execute(text("SELECT DISTINCT vendor FROM contracts WHERE status='draft' AND vendor NOT IN (SELECT vendor FROM contracts WHERE status <> 'draft') ORDER BY 1"))]
        nda_only = [r[0] for r in s.execute(text("SELECT vendor FROM contracts WHERE status <> 'draft' GROUP BY vendor HAVING bool_and(type IN ('NDA','DPA')) ORDER BY 1"))]
        unsigned = [dict(r) for r in s.execute(text("SELECT contract_id, title, vendor, total_value, annual_value, category FROM v_effective_terms WHERE status <> 'draft' AND fully_executed IS NOT TRUE AND COALESCE(total_value, annual_value) > 0 ORDER BY contract_id")).mappings()]
        draft_value = {r[0]: float(r[1] or 0) for r in s.execute(text("SELECT vendor, max(annual_value) FROM contracts WHERE status='draft' GROUP BY 1"))}
    byc = {c["contract_id"]: c for c in cons}
    for u in unsigned[:1]:
        c = byc.get(u["contract_id"])
        if c:
            inv(c, today - timedelta(days=7), float(u["total_value"] or u["annual_value"]) * 0.30, "Milestone invoice (30% of fixed fee)", force_unpaid=True)
    for v in draft_only[:1]:
        base = round(draft_value.get(v, 0) / 12, -3) or 85000
        for k in range(3):
            d0 = _add_months(date(today.year, today.month, 28), -(3 - k))
            inv(None, d0, base, f"Managed services – {d0:%B %Y}", vendor=v, title="", no=f"{v[:3].upper()}-{d0:%y%m}-{k + 1:03d}")
    for v in nda_only[:1]:
        inv(None, today - timedelta(days=50), 48000, "Professional services (no statement of work on file)", vendor=v, title="", no=f"{v[:3].upper()}-{(today - timedelta(days=50)):%y%m}-014")
    sows = sorted({i["contract_title"] for i in invoices if i["contract_title"]}, key=lambda t: -sum(x["amount"] for x in invoices if x["contract_title"] == t))
    recurring = [t for t in sows if sum(1 for x in invoices if x["contract_title"] == t) >= 5]
    for t in recurring[:1]:                       # the biggest recurring contract: two invoices well above the usual
        for i in [x for x in invoices if x["contract_title"] == t][-3:-1]:
            i["amount"] = round(i["amount"] * 1.45, 2)
            i["description"] += " (includes out-of-scope change requests)"
    for t in recurring[1:2]:                      # the next one: a duplicated invoice
        dup = next(x for x in invoices if x["contract_title"] == t)
        n += 1
        invoices.append({**dup, "external_id": f"INV-{n:05d}"})
    saas = [c for c in cons if c["type"] == "SaaS" and c["annual_value"] and any(i["contract_title"] == c["title"] for i in invoices)]
    def plan(c):
        return float(c["annual_value"]) * (c["expiry_date"] - c["effective_date"]).days / 365.0

    for c in sorted(saas, key=plan)[:1]:          # a true-up that takes billing to 110% of the contract's planned value
        billed = sum(i["amount"] for i in invoices if i["contract_title"] == c["title"])
        if plan(c) * 1.1 > billed:
            inv(c, today - timedelta(days=9), plan(c) * 1.1 - billed, "Additional seats true-up", force_unpaid=True)
    for c in saas[:1]:                            # first invoice dated before the contract starts
        first = next(i for i in invoices if i["contract_title"] == c["title"])
        first["invoice_date"], first["period_start"] = c["effective_date"] - timedelta(days=21), c["effective_date"] - timedelta(days=21)
        first["due_date"] = first["invoice_date"] + timedelta(days=int(c["payment_terms_days"] or 45))
    late_vendor = next(iter(sorted({c["vendor"] for c in cons if c["type"] == "SOW"})[1:2]), None)
    for i in invoices:                            # one vendor is paid late by us
        if late_vendor and i["vendor"] == late_vendor and i["paid_date"] and int(i["external_id"][-2:]) % 3 == 1:
            i["paid_date"] = date.fromisoformat(str(i["due_date"])) + timedelta(days=17)
    # ---- SLA actuals: targets come from the contracts; a few months miss them (chosen by rule)
    sla = []
    sla_contracts = [c for c in cons if sla_t.get((c["contract_id"], "sla_availability_pct")) is not None]
    breach_plan = {0: {-3: 0.38, -2: 0.19}, 1: {-1: 0.49, -4: 0.12}, 2: {-2: 0.06}}
    for ix, c in enumerate(sla_contracts):
        tgt = sla_t[(c["contract_id"], "sla_availability_pct")]
        for back in range(-8, 0):
            ps = _add_months(date(today.year, today.month, 1), back)
            if ps < date(c["effective_date"].year, c["effective_date"].month, 1):
                continue
            miss = breach_plan.get(ix, {}).get(back)
            actual = round(tgt - miss, 2) if miss else round(min(100.0, tgt + rnd.uniform(0.02, 0.35)), 2)
            sla.append(dict(contract_title=c["title"], vendor=c["vendor"], metric_key="sla_availability_pct", period=ps, actual=actual, incidents=1 if actual < tgt else rnd.choice([0, 0, 0, 1]), note="Breach: service credit claim" if actual < tgt else ""))
    inc_contracts = [c for c in cons if sla_t.get((c["contract_id"], "incident_notice_hours")) is not None]
    for ix, c in enumerate(inc_contracts):
        it = sla_t[(c["contract_id"], "incident_notice_hours")]
        for back in (-3, -2, -1):
            ps = _add_months(date(today.year, today.month, 1), back)
            if ps < date(c["effective_date"].year, c["effective_date"].month, 1):
                continue
            bad = ix == 1 and back == -2
            sla.append(dict(contract_title=c["title"], vendor=c["vendor"], metric_key="incident_notice_hours", period=ps, actual=round(it * 1.5) if bad else rnd.choice([6, 12, 20, 30]), incidents=1, note="Notified late" if bad else ""))
    # ---- obligation status: past milestones were delivered, except the latest one on two contracts
    status, over = [], set()
    past_by: dict[int, list] = {}
    for m in ms:
        if m["due_date"] < today:
            past_by.setdefault(m["contract_id"], []).append(m)
    for cid in sorted(past_by)[:2]:
        over.add((cid, past_by[cid][-1]["key"]))
    for m in ms:
        if m["due_date"] < today and (m["contract_id"], m["key"]) not in over:
            status.append(dict(contract_title=m["title"], vendor=m["vendor"], key=m["key"], status="done", completed_on=m["due_date"] + timedelta(days=rnd.randint(-4, 6)), note="Accepted by the business"))
    return invoices, sla, status


# ------------------------------------------------------------------ loader
def _d(v) -> date | None:
    if isinstance(v, date):
        return v
    return date.fromisoformat(v) if v and str(v).strip() else None


class ContractIndex:
    """Find the contract a feed row refers to: exact title, normalised title, a reference that contains a title, or - when the row names only a
    vendor - the vendor's single contract that carries a value. Real exports carry PO / contract references of many shapes; this keeps the matching generic."""

    def __init__(self, s):
        rows = [dict(r) for r in s.execute(text("SELECT id, title, vendor, type, COALESCE(total_value, annual_value) AS value FROM contracts WHERE status <> 'draft'")).mappings()]
        self.rows = rows
        self.exact = {r["title"]: r["id"] for r in rows}
        self.norm = {self._n(r["title"]): r["id"] for r in rows}

    @staticmethod
    def _n(t: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()

    def match(self, vendor: str | None, ref: str | None) -> int | None:
        """Vendor first (titles such as 'Statement of Work No. 1' repeat across vendors), then the reference within that vendor's contracts."""
        ref = (ref or "").strip()
        v = self._n(vendor) if vendor else ""
        pool = [r for r in self.rows if v and (self._n(r["vendor"]) == v or self._n(r["vendor"]).split()[0] == v.split()[0])] or self.rows
        if ref:
            n = self._n(ref)
            for key in (lambda r: r["title"] == ref, lambda r: self._n(r["title"]) == n):
                hits = [r["id"] for r in pool if key(r)]
                if len(hits) == 1:
                    return hits[0]
            hits = [r["id"] for r in pool if n and (n in self._n(r["title"]) or self._n(r["title"]) in n)]
            return hits[0] if len(hits) == 1 else None
        if vendor:
            vs = [r for r in pool if r["value"]]
            if len(vs) == 1:
                return vs[0]["id"]
        return None


def load_csv(name: str, content: str) -> dict:
    """Load one CSV feed (by file name) into the tables; idempotent. Returns counts."""
    return apply_rows(name, list(csv.DictReader(io.StringIO(content))))


def _milestone_key(s, cid: int | None, r: dict) -> str | None:
    """The obligation an acceptance certificate refers to: same due date, else the milestone whose title shares the most words."""
    if not cid:
        return None
    obs = [dict(x) for x in s.execute(text("SELECT key, title, due_date FROM obligations WHERE contract_id=:c AND kind='milestone'"), {"c": cid}).mappings()]
    if r.get("due"):
        same = [o for o in obs if o["due_date"] == _d(r["due"])]
        if len(same) == 1:
            return same[0]["key"]
        obs = same or obs
    words = set(re.findall(r"[a-z]{4,}", (r.get("milestone") or "").lower()))
    best = max(obs, key=lambda o: len(words & set(re.findall(r"[a-z]{4,}", o["title"].lower()))), default=None)
    return best["key"] if best and words & set(re.findall(r"[a-z]{4,}", best["title"].lower())) else None


def apply_rows(name: str, rows: list[dict]) -> dict:
    cnt = dict(rows=len(rows), new=0, updated=0, skipped=0, unmatched=0)
    with SessionLocal() as s:
        ids = ContractIndex(s)
        for r in rows:
            try:
                if name.startswith("invoice"):
                    cid = ids.match(r.get("vendor"), r.get("contract_title"))
                    if r.get("contract_title") and not cid:
                        cnt["unmatched"] += 1
                    if not r.get("vendor") or not r.get("amount"):
                        cnt["skipped"] += 1
                        continue
                    r["external_id"] = r.get("external_id") or f"{r['vendor']}|{r.get('invoice_no')}|{r['amount']}"
                    ex = s.execute(text("SELECT 1 FROM invoices WHERE external_id=:e"), {"e": r["external_id"]}).first()
                    s.execute(text("""INSERT INTO invoices (external_id, vendor, contract_id, contract_ref, invoice_no, invoice_date, period_start, period_end, due_date, paid_date, amount, description, category)
                                      VALUES (:e,:v,:c,:ref,:no,:d,:ps,:pe,:due,:paid,:a,:desc,:cat)
                                      ON CONFLICT (external_id) DO UPDATE SET vendor=EXCLUDED.vendor, contract_id=EXCLUDED.contract_id, invoice_no=EXCLUDED.invoice_no, invoice_date=EXCLUDED.invoice_date,
                                        period_start=EXCLUDED.period_start, period_end=EXCLUDED.period_end, due_date=EXCLUDED.due_date, paid_date=EXCLUDED.paid_date, amount=EXCLUDED.amount,
                                        description=EXCLUDED.description, category=EXCLUDED.category"""),
                              {"e": r["external_id"], "v": r["vendor"], "c": cid, "ref": r.get("contract_title") or None, "no": r.get("invoice_no"), "d": _d(r["invoice_date"]),
                               "ps": _d(r.get("period_start")), "pe": _d(r.get("period_end")), "due": _d(r.get("due_date")), "paid": _d(r.get("paid_date")),
                               "a": r["amount"], "desc": r.get("description"), "cat": r.get("category")})
                elif name.startswith("sla"):
                    cid = ids.match(r.get("vendor"), r["contract_title"])
                    if not cid:
                        cnt["unmatched"] += 1
                        continue
                    ex = s.execute(text("SELECT 1 FROM sla_measurements WHERE contract_id=:c AND metric_key=:k AND period=:p"), {"c": cid, "k": r["metric_key"], "p": _d(r["period"])}).first()
                    s.execute(text("""INSERT INTO sla_measurements (contract_id, metric_key, period, actual, incidents, note) VALUES (:c,:k,:p,:a,:i,:n)
                                      ON CONFLICT (contract_id, metric_key, period) DO UPDATE SET actual=EXCLUDED.actual, incidents=EXCLUDED.incidents, note=EXCLUDED.note"""),
                              {"c": cid, "k": r["metric_key"], "p": _d(r["period"]), "a": r["actual"], "i": int(r.get("incidents") or 0), "n": r.get("note") or None})
                elif name.startswith("obligation"):
                    cid = ids.match(r.get("vendor"), r["contract_title"])
                    r["key"] = r.get("key") or _milestone_key(s, cid, r)
                    if not r["key"]:
                        cnt["unmatched"] += 1
                        continue
                    res = s.execute(text("UPDATE obligations SET status=:st, completed_on=:d, note=COALESCE(:n, note), updated_at=now() WHERE contract_id=:c AND key=:k AND (status <> :st OR completed_on IS DISTINCT FROM :d)"),
                                    {"st": r["status"], "d": _d(r.get("completed_on")), "n": r.get("note") or None, "c": cid, "k": r["key"]})
                    ex = None if res.rowcount else True
                    if res.rowcount:
                        cnt["updated"] += 1
                    else:
                        cnt["skipped"] += 1
                    continue
                else:
                    cnt["skipped"] += 1
                    continue
                cnt["updated" if ex else "new"] += 1
            except (KeyError, ValueError):
                cnt["skipped"] += 1
        s.commit()
    return cnt


def recompute() -> dict:
    with SessionLocal() as s:
        n = spend.compute_exceptions(s)
        v = risk.compute_all(s)
        s.commit()
    return {"exceptions": n, "vendors_scored": v}


def run_feeds(trigger: str = "manual") -> dict:
    """The 'feeds' pipeline: load every CSV in data/feeds/ (idempotent), then refresh spend exceptions and risk scores."""
    from app import pipeline

    if not pipeline._lock.acquire(blocking=False):
        return {"status": "busy", "message": "a pipeline run is already in progress"}
    t0 = time.time()
    try:
        d = feeds_dir()
        d.mkdir(parents=True, exist_ok=True)
        files = feed_files()
        with SessionLocal() as s:
            rid = s.execute(text("INSERT INTO pipeline_runs (trigger, pipeline) VALUES (:t,'feeds') RETURNING id"), {"t": trigger}).scalar()
            s.commit()
        tot = dict(new=0, updated=0, skipped=0)
        failed = 0
        for f in files:
            try:
                if f.suffix.lower() == ".csv":
                    c = load_csv(f.name, f.read_text())
                else:
                    kind, rows = _read_document(f)
                    c = apply_rows(FEED_OF[kind], rows)
                for k in tot:
                    tot[k] += c[k]
                detail = f"{c['rows']} rows: {c['new']} new, {c['updated']} updated" + (f", {c['unmatched']} without a matching contract" if c["unmatched"] else "")
                act = "new" if c["new"] else "updated" if c["updated"] else "unchanged"
            except Exception as e:
                failed += 1
                detail, act = f"{type(e).__name__}: {e}"[:300], "failed"
            with SessionLocal() as s:
                s.execute(text("INSERT INTO pipeline_events (run_id, path, action, detail) VALUES (:r,:p,:a,:d)"), {"r": rid, "p": f"feeds/{f.relative_to(d)}", "a": act, "d": detail})
                s.commit()
        res = recompute()
        with SessionLocal() as s:
            fp = hashlib.sha1("".join(f"{f.name}{f.stat().st_size}{f.stat().st_mtime_ns}" for f in files).encode()).hexdigest()
            s.execute(text("UPDATE pipeline_runs SET finished_at=now(), status=:st, scanned=:a, new_docs=:b, updated=:c, unchanged=:d, failed=:e, message=:m WHERE id=:i"),
                      {"st": "failed" if failed and not (tot["new"] + tot["updated"]) else "completed", "a": len(files), "b": tot["new"], "c": tot["updated"], "d": tot["skipped"], "e": failed,
                       "m": f"{res['exceptions']} spend exceptions, {res['vendors_scored']} vendors scored", "i": rid})
            s.execute(text("UPDATE pipeline_config SET last_run_at=now(), next_run_at=now() + make_interval(mins => interval_minutes), last_fingerprint=:f WHERE key='feeds'"), {"f": fp})
            if trigger == "watch" and not (tot["new"] or tot["updated"] or failed):
                s.execute(text("DELETE FROM pipeline_runs WHERE id=:i"), {"i": rid})
            s.commit()
        return {"status": "completed", "run_id": rid, "seconds": round(time.time() - t0, 2), "scanned": len(files), "new_docs": tot["new"], "updated": tot["updated"], "unchanged": tot["skipped"], "failed": failed, **res}
    finally:
        pipeline._lock.release()
