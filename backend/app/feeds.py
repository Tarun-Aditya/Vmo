"""Operational feeds: invoices (ERP / AP export), SLA measurements (monitoring / ITSM export) and obligation status updates.
Real feeds are CSV files dropped in data/feeds/ and loaded by the 'feeds' pipeline. For the demo, `generate()` writes believable
fictional feeds for the seeded contracts (with planted problems) so spend, SLA and risk screens have data."""
from __future__ import annotations

import csv
import hashlib
import io
import random
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


def _add_months(d: date, n: int) -> date:
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    for day in (d.day, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


# ------------------------------------------------------------------ demo feed generator
def generate(today: date | None = None, seed: int = 11) -> dict:
    today = today or date.today()
    rnd = random.Random(seed)
    with SessionLocal() as s:
        cons = [dict(r) for r in s.execute(text(
            "SELECT t.contract_id, t.title, t.vendor, t.type, t.category, t.effective_date, t.expiry_date, t.annual_value, t.total_value, t.payment_terms_days "
            "FROM v_effective_terms t WHERE t.status <> 'draft' ORDER BY t.contract_id")).mappings()]
        sla_t = {(r[0], r[1]): float(r[2]) for r in s.execute(text("SELECT contract_id, metric_key, value_num FROM extracted_values WHERE metric_key IN ('sla_availability_pct','incident_notice_hours')"))}
        ms = [dict(r) for r in s.execute(text("SELECT o.contract_id, c.title, o.key, o.due_date FROM obligations o JOIN contracts c ON c.id=o.contract_id WHERE o.kind='milestone' ORDER BY o.contract_id, o.due_date")).mappings()]
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
        late = 17 if "Delmont" in c["vendor"] and c["type"] == "SOW" else 0
        if c["type"] == "SaaS" and ann:
            step = 3 if "Nginova" in c["vendor"] else 12
            k = 0
            while _add_months(eff, k) <= today and _add_months(eff, k) < exp:
                d = _add_months(eff, k)
                inv(c, d, float(ann) * step / 12, f"Subscription {d:%b %Y} – {_add_months(d, step):%b %Y}", d, _add_months(d, step) - timedelta(days=1))
                k += step
        elif c["type"] == "SOW" and ann:
            k = 0
            while _add_months(eff, k + 1) + timedelta(days=5) <= today and _add_months(eff, k + 1) <= exp:
                ps, pe = _add_months(eff, k), _add_months(eff, k + 1) - timedelta(days=1)
                inv(c, pe + timedelta(days=5), float(ann) / 12, f"Services {ps:%d %b} – {pe:%d %b %Y}", ps, pe, paid_extra=late if k % 3 == 1 else 0)
                k += 1
        elif c["type"] == "Work Order" and tot:
            term = (exp - eff).days
            for frac, pct in ((0.25, 0.30), (0.60, 0.40), (1.0, 0.30)):
                d = eff + timedelta(days=int(term * frac))
                if d <= today:
                    inv(c, d, float(tot) * pct, f"Milestone invoice ({int(pct * 100)}% of fixed fee)")
    # ---- planted problems (each one is a demo story)
    def find(sub):
        return next((c for c in cons if sub in c["title"]), None)

    sow1 = find("SOW 1 – Application Managed Services")
    mine = [i for i in invoices if i["contract_title"] == (sow1 or {}).get("title")]
    for i in mine[-3:-1]:
        i["amount"] = round(i["amount"] * 1.45, 2)
        i["description"] += " (includes out-of-scope change requests)"
    wo2 = find("Work Order 2 – Endpoint Security")
    if wo2:
        inv(wo2, date(2026, 10, 30), float(wo2["total_value"]) * 0.30, "Milestone invoice (30% of fixed fee)", force_unpaid=True)
    for k in range(3):
        d = date(2026, 8 + k, 28)
        inv(None, d, 85000, f"Managed hosting – {d:%B %Y}", vendor="Orbitline Cloud Hosting Inc", title="", no=f"ORB-{d:%y%m}-{k + 1:03d}")
    inv(None, date(2026, 9, 18), 48000, "Penetration test – external perimeter", vendor="Skyguard Security Solutions Inc", title="", no="SKY-2609-014")
    tar = find("SOW 1 – Application Development and Maintenance")
    dup = next((i for i in invoices if i["contract_title"] == (tar or {}).get("title")), None)
    if dup:
        n += 1
        invoices.append({**dup, "external_id": f"INV-{n:05d}"})
    pulse = find("PulseHR")
    if pulse:
        inv(pulse, date(2026, 10, 29), 65000, "Additional seats true-up (200 users)", force_unpaid=True)
    led = find("Ledgerline Finance Cloud")
    if led and led["type"] == "SaaS":
        first = next((i for i in invoices if i["contract_title"] == led["title"]), None)
        if first:
            first["invoice_date"], first["period_start"] = date(2025, 12, 30), date(2025, 12, 30)
            first["due_date"] = first["invoice_date"] + timedelta(days=int(led["payment_terms_days"] or 45))
    # ---- SLA actuals
    sla = []
    breaches = {("Nginova", -3): 99.12, ("Nginova", -2): 99.31, ("PulseHR", -1): 99.41, ("PulseHR", -4): 99.78, ("AdSpark", -2): 99.84}
    for c in cons:
        tgt = sla_t.get((c["contract_id"], "sla_availability_pct"))
        if tgt is None:
            continue
        for back in range(-8, 0):
            ps = _add_months(date(today.year, today.month, 1), back)
            if ps < date(c["effective_date"].year, c["effective_date"].month, 1):
                continue
            actual = next((v for (name, b), v in breaches.items() if name in c["vendor"] and b == back), None) or round(min(100.0, tgt + rnd.uniform(0.02, 0.35)), 2)
            sla.append(dict(contract_title=c["title"], metric_key="sla_availability_pct", period=ps, actual=actual, incidents=1 if actual < tgt else rnd.choice([0, 0, 0, 1]), note="Breach: service credit claim" if actual < tgt else ""))
        it = sla_t.get((c["contract_id"], "incident_notice_hours"))
        if it:
            for back in (-3, -2, -1):
                ps = _add_months(date(today.year, today.month, 1), back)
                if ps < date(c["effective_date"].year, c["effective_date"].month, 1):
                    continue
                bad = "Ledgerline" in c["vendor"] and back == -2
                sla.append(dict(contract_title=c["title"], metric_key="incident_notice_hours", period=ps, actual=71 if bad else rnd.choice([6, 12, 20, 30]), incidents=1, note="Notified late" if bad else ""))
    # ---- obligation status: past milestones were delivered, except two planted overdue ones
    status, over = [], set()
    for sub in ("SOW 1 – Application Managed Services", "SOW 1 – Application Development and Maintenance"):
        c = find(sub)
        past = [m for m in ms if c and m["contract_id"] == c["contract_id"] and m["due_date"] < today]
        if past:
            over.add((past[-1]["contract_id"], past[-1]["key"]))
    for m in ms:
        if m["due_date"] < today and (m["contract_id"], m["key"]) not in over:
            status.append(dict(contract_title=m["title"], key=m["key"], status="done", completed_on=m["due_date"] + timedelta(days=rnd.randint(-4, 6)), note="Accepted by the business"))
    d = feeds_dir()
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*.csv"):         # a seed starts from a clean feeds folder
        old.unlink()
    for name, cols, rows in (("invoices.csv", INVOICE_COLS, invoices), ("sla_measurements.csv", SLA_COLS, sla), ("obligation_status.csv", STATUS_COLS, status)):
        with (d / name).open("w", newline="") as f:
            w = csv.DictWriter(f, cols)
            w.writeheader()
            w.writerows(rows)
    return {"invoices": len(invoices), "sla": len(sla), "status": len(status)}


# ------------------------------------------------------------------ loader
def _d(v: str | None) -> date | None:
    return date.fromisoformat(v) if v and v.strip() else None


def load_csv(name: str, content: str) -> dict:
    """Load one feed (by file name) into the tables; idempotent. Returns counts."""
    rows = list(csv.DictReader(io.StringIO(content)))
    cnt = dict(rows=len(rows), new=0, updated=0, skipped=0, unmatched=0)
    with SessionLocal() as s:
        ids = {r[0]: r[1] for r in s.execute(text("SELECT title, id FROM contracts"))}
        for r in rows:
            try:
                if name.startswith("invoice"):
                    cid = ids.get((r.get("contract_title") or "").strip())
                    if r.get("contract_title") and not cid:
                        cnt["unmatched"] += 1
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
                    cid = ids.get(r["contract_title"].strip())
                    if not cid:
                        cnt["unmatched"] += 1
                        continue
                    ex = s.execute(text("SELECT 1 FROM sla_measurements WHERE contract_id=:c AND metric_key=:k AND period=:p"), {"c": cid, "k": r["metric_key"], "p": _d(r["period"])}).first()
                    s.execute(text("""INSERT INTO sla_measurements (contract_id, metric_key, period, actual, incidents, note) VALUES (:c,:k,:p,:a,:i,:n)
                                      ON CONFLICT (contract_id, metric_key, period) DO UPDATE SET actual=EXCLUDED.actual, incidents=EXCLUDED.incidents, note=EXCLUDED.note"""),
                              {"c": cid, "k": r["metric_key"], "p": _d(r["period"]), "a": r["actual"], "i": int(r.get("incidents") or 0), "n": r.get("note") or None})
                elif name.startswith("obligation"):
                    cid = ids.get(r["contract_title"].strip())
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
        files = sorted(d.glob("*.csv"))
        with SessionLocal() as s:
            rid = s.execute(text("INSERT INTO pipeline_runs (trigger, pipeline) VALUES (:t,'feeds') RETURNING id"), {"t": trigger}).scalar()
            s.commit()
        tot = dict(new=0, updated=0, skipped=0)
        failed = 0
        for f in files:
            try:
                c = load_csv(f.name, f.read_text())
                for k in tot:
                    tot[k] += c[k]
                detail = f"{c['rows']} rows: {c['new']} new, {c['updated']} updated" + (f", {c['unmatched']} without a matching contract" if c["unmatched"] else "")
                act = "new" if c["new"] else "updated" if c["updated"] else "unchanged"
            except Exception as e:
                failed += 1
                detail, act = f"{type(e).__name__}: {e}"[:300], "failed"
            with SessionLocal() as s:
                s.execute(text("INSERT INTO pipeline_events (run_id, path, action, detail) VALUES (:r,:p,:a,:d)"), {"r": rid, "p": f"feeds/{f.name}", "a": act, "d": detail})
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
