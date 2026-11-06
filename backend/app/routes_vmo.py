"""VMO depth API: obligations and SLAs, spend vs contract, vendor risk scorecards, term benchmarks, feed upload."""
from __future__ import annotations

import statistics
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import feeds, risk
from app.db import SessionLocal

router = APIRouter(prefix="/api")


def rows(sql: str, **p) -> list[dict]:
    with SessionLocal() as s:
        return [dict(r) for r in s.execute(text(sql), p).mappings().all()]


def one(sql: str, **p):
    r = rows(sql, **p)
    return r[0] if r else None


def _refresh():
    with SessionLocal() as s:
        risk.compute_all(s)
        s.commit()


# ------------------------------------------------------------------ obligations
@router.get("/obligations")
def obligations(status: str | None = None, kind: str | None = None, vendor: str | None = None, party: str | None = None, contract_id: int | None = None, q: str | None = None):
    data = rows("""SELECT obligation_id, contract_id, title AS contract, vendor, type, kind, party, obligation, due_date, frequency, target_value, target_unit, status, completed_on, days_left, source
                   FROM v_obligations
                   WHERE contract_status <> 'draft' AND (CAST(:st AS text) IS NULL OR status = :st) AND (CAST(:k AS text) IS NULL OR kind = :k)
                     AND (CAST(:v AS text) IS NULL OR vendor = :v) AND (CAST(:p AS text) IS NULL OR party = :p) AND (CAST(:c AS int) IS NULL OR contract_id = :c)
                     AND (CAST(:q AS text) IS NULL OR obligation ILIKE :qq OR title ILIKE :qq)
                   ORDER BY CASE status WHEN 'overdue' THEN 0 WHEN 'open' THEN 1 ELSE 2 END, due_date NULLS LAST, vendor, obligation""",
                st=status, k=kind, v=vendor, p=party, c=contract_id, q=q, qq=f"%{q}%" if q else None)
    summ = one("""SELECT count(*) FILTER (WHERE status='open') AS open, count(*) FILTER (WHERE status='overdue') AS overdue,
                         count(*) FILTER (WHERE status='open' AND days_left BETWEEN 0 AND 30) AS due_30, count(*) FILTER (WHERE status='done') AS done,
                         count(*) FILTER (WHERE due_date IS NULL AND status='open') AS ongoing
                  FROM v_obligations WHERE contract_status <> 'draft'""")
    return {"rows": data, "summary": summ, "kinds": [r["kind"] for r in rows("SELECT DISTINCT kind FROM obligations ORDER BY 1")],
            "vendors": [r["vendor"] for r in rows("SELECT DISTINCT vendor FROM v_obligations WHERE contract_status <> 'draft' ORDER BY 1")]}


class ObligationPatch(BaseModel):
    status: str
    note: str | None = None
    completed_on: date | None = None


@router.patch("/obligations/{oid}")
def obligation_patch(oid: int, b: ObligationPatch):
    if b.status not in ("open", "done", "waived"):
        raise HTTPException(422, "status must be open, done or waived")
    done_on = b.completed_on or (date.today() if b.status == "done" else None)
    with SessionLocal() as s:
        r = s.execute(text("UPDATE obligations SET status=:s, note=COALESCE(:n, note), completed_on=:d, updated_at=now() WHERE id=:i"),
                      {"s": b.status, "n": b.note, "d": done_on if b.status == "done" else None, "i": oid})
        if not r.rowcount:
            raise HTTPException(404, "obligation not found")
        s.commit()
    _refresh()
    return one("SELECT * FROM v_obligations WHERE obligation_id=:i", i=oid)


# ------------------------------------------------------------------ SLA
def _credit(shortfall: float, metric: str) -> float:
    """Typical service-credit tiers (share of the monthly fee). The clause's own tiers are not extracted, so this is an estimate."""
    if metric != "sla_availability_pct":
        return 0.0
    return 0.05 if shortfall < 0.5 else 0.10 if shortfall < 1.0 else 0.20


@router.get("/sla")
def sla(vendor: str | None = None):
    pts = rows("""SELECT s.contract_id, s.title, s.vendor, s.metric_key, s.period, s.actual, s.target, s.breach, s.shortfall, s.incidents, t.annual_value
                  FROM v_sla s JOIN v_effective_terms t ON t.contract_id = s.contract_id WHERE (CAST(:v AS text) IS NULL OR s.vendor = :v) ORDER BY s.contract_id, s.metric_key, s.period""", v=vendor)
    series: dict[tuple, dict] = {}
    for p in pts:
        k = (p["contract_id"], p["metric_key"])
        e = series.setdefault(k, {"contract_id": p["contract_id"], "title": p["title"], "vendor": p["vendor"], "metric_key": p["metric_key"], "target": float(p["target"]) if p["target"] is not None else None,
                                  "unit": "%" if p["metric_key"] == "sla_availability_pct" else "hours", "points": [], "breaches": 0, "credit_usd": 0.0})
        credit = _credit(float(p["shortfall"] or 0), p["metric_key"]) * float(p["annual_value"] or 0) / 12 if p["breach"] else 0.0
        e["points"].append({"period": p["period"], "actual": float(p["actual"]), "breach": bool(p["breach"]), "incidents": p["incidents"], "credit_usd": round(credit)})
        e["breaches"] += int(bool(p["breach"]))
        e["credit_usd"] += credit
    out = sorted(series.values(), key=lambda e: (-e["breaches"], e["vendor"]))
    for e in out:
        e["credit_usd"] = round(e["credit_usd"])
    return {"series": out, "summary": {"contracts": len({e["contract_id"] for e in out}), "breach_months": sum(e["breaches"] for e in out),
                                       "credit_usd": sum(e["credit_usd"] for e in out), "compliant": sum(1 for e in out if not e["breaches"])}}


class Measurement(BaseModel):
    contract_id: int
    metric_key: str
    period: date
    actual: float
    incidents: int = 0
    note: str | None = None


@router.post("/sla/measurements")
def sla_add(m: Measurement):
    if m.metric_key not in ("sla_availability_pct", "incident_notice_hours"):
        raise HTTPException(422, "metric_key must be sla_availability_pct or incident_notice_hours")
    with SessionLocal() as s:
        s.execute(text("""INSERT INTO sla_measurements (contract_id, metric_key, period, actual, incidents, note, source) VALUES (:c,:k,:p,:a,:i,:n,'manual')
                          ON CONFLICT (contract_id, metric_key, period) DO UPDATE SET actual=:a, incidents=:i, note=:n, source='manual'"""),
                  {"c": m.contract_id, "k": m.metric_key, "p": m.period.replace(day=1), "a": m.actual, "i": m.incidents, "n": m.note})
        s.commit()
    _refresh()
    return {"saved": True}


# ------------------------------------------------------------------ spend
@router.get("/spend/summary")
def spend_summary():
    tot = one("""SELECT COALESCE(sum(amount),0) AS billed, COALESCE(sum(amount) FILTER (WHERE invoice_date >= CURRENT_DATE - 90),0) AS billed_90d, count(*) AS invoices,
                        COALESCE(sum(amount) FILTER (WHERE contract_id IS NULL),0) AS off_contract FROM invoices""")
    ex = one("SELECT count(*) AS n, COALESCE(sum(amount_at_risk),0) AS at_risk, count(*) FILTER (WHERE severity IN ('critical','high')) AS serious FROM spend_exceptions")
    plan = one("SELECT COALESCE(sum(planned_value),0) AS planned FROM v_contract_spend")
    by_vendor = rows("""SELECT v.vendor, COALESCE(i.billed,0) AS billed, COALESCE(p.planned,0) AS planned, COALESCE(e.n,0) AS exceptions, COALESCE(e.risk,0) AS at_risk
                        FROM (SELECT DISTINCT vendor FROM invoices UNION SELECT DISTINCT vendor FROM contracts WHERE status <> 'draft') v
                        LEFT JOIN (SELECT vendor, sum(amount) AS billed FROM invoices GROUP BY 1) i USING (vendor)
                        LEFT JOIN (SELECT vendor, sum(planned_value) AS planned FROM v_contract_spend GROUP BY 1) p USING (vendor)
                        LEFT JOIN (SELECT vendor, count(*) AS n, sum(amount_at_risk) AS risk FROM spend_exceptions GROUP BY 1) e USING (vendor)
                        WHERE COALESCE(i.billed,0) > 0 ORDER BY billed DESC""")
    monthly = rows("""SELECT to_char(date_trunc('month', invoice_date), 'YYYY-MM') AS month, sum(amount) FILTER (WHERE contract_id IS NOT NULL) AS on_contract,
                             sum(amount) FILTER (WHERE contract_id IS NULL) AS off_contract FROM invoices WHERE invoice_date >= date_trunc('month', CURRENT_DATE) - interval '11 months'
                      GROUP BY 1 ORDER BY 1""")
    by_kind = rows("SELECT kind, severity, count(*) AS n, sum(amount_at_risk) AS at_risk FROM spend_exceptions GROUP BY 1,2 ORDER BY at_risk DESC")
    return {"billed": tot["billed"], "billed_90d": tot["billed_90d"], "invoices": tot["invoices"], "off_contract": tot["off_contract"], "planned": plan["planned"],
            "exceptions": ex["n"], "at_risk": ex["at_risk"], "serious": ex["serious"], "by_vendor": by_vendor, "monthly": monthly, "by_kind": by_kind}


@router.get("/spend/contracts")
def spend_contracts(vendor: str | None = None):
    return rows("""SELECT s.contract_id, s.title, s.vendor, s.type, s.effective_date, s.expiry_date, s.planned_value, s.billed, s.invoices, s.last_invoice, s.elapsed_pct, s.expected_to_date, s.pct_of_planned,
                          (SELECT count(*) FROM spend_exceptions e WHERE e.contract_id = s.contract_id) AS exceptions
                   FROM v_contract_spend s WHERE (CAST(:v AS text) IS NULL OR s.vendor = :v) ORDER BY s.billed DESC, s.title""", v=vendor)


@router.get("/spend/exceptions")
def spend_exceptions(kind: str | None = None, severity: str | None = None, vendor: str | None = None):
    return rows("""SELECT exception_id, kind, severity, amount_at_risk, detail, vendor, contract_id, contract_title, invoice_no, invoice_date, invoice_amount FROM v_spend_exceptions
                   WHERE (CAST(:k AS text) IS NULL OR kind = :k) AND (CAST(:s AS text) IS NULL OR severity = :s) AND (CAST(:v AS text) IS NULL OR vendor = :v)
                   ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, amount_at_risk DESC""", k=kind, s=severity, v=vendor)


@router.get("/invoices")
def invoices(contract_id: int | None = None, vendor: str | None = None):
    return rows("""SELECT invoice_id, vendor, contract_id, contract_title, invoice_no, invoice_date, due_date, paid_date, amount, description, days_paid_late FROM v_invoices
                   WHERE (CAST(:c AS int) IS NULL OR contract_id = :c) AND (CAST(:v AS text) IS NULL OR vendor = :v) ORDER BY invoice_date DESC LIMIT 300""", c=contract_id, v=vendor)


class FeedUpload(BaseModel):
    name: str
    content: str


@router.post("/feeds/upload")
def feed_upload(u: FeedUpload):
    """Drop a CSV (invoices / sla / obligation status) into the feeds folder and load it now."""
    low = u.name.lower()
    if not low.endswith(".csv") or not low.startswith(("invoice", "sla", "obligation")):
        raise HTTPException(422, "name the file invoices*.csv, sla*.csv or obligation_status*.csv")
    d = feeds.feeds_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / u.name).write_text(u.content)
    res = feeds.run_feeds("upload")
    return res


# ------------------------------------------------------------------ risk
@router.get("/risk/vendors")
def risk_vendors():
    data = rows("""SELECT s.vendor, s.score, s.tier, s.components, (SELECT count(*) FROM contracts c WHERE c.vendor = s.vendor AND c.status <> 'draft') AS documents,
                          (SELECT COALESCE(sum(annual_value),0) FROM v_effective_terms t WHERE t.vendor = s.vendor AND t.status <> 'draft') AS annual_value
                   FROM vendor_scores s ORDER BY s.score DESC""")
    return {"vendors": data, "weights": rows("SELECT key, label, description, weight, enabled FROM risk_weights ORDER BY sort_order"),
            "tiers": [{"min": 50, "tier": "critical"}, {"min": 30, "tier": "high"}, {"min": 15, "tier": "medium"}, {"min": 0, "tier": "low"}]}


@router.get("/risk/vendors/{vendor}")
def risk_vendor(vendor: str):
    sc = one("SELECT vendor, score, tier, components, computed_at FROM vendor_scores WHERE vendor=:v", v=vendor)
    if not sc:
        raise HTTPException(404, "vendor not scored")
    return {**sc, "weights": rows("SELECT key, label, weight FROM risk_weights WHERE enabled ORDER BY sort_order"),
            "exceptions": rows("SELECT kind, severity, amount_at_risk, detail FROM v_spend_exceptions WHERE vendor=:v ORDER BY amount_at_risk DESC LIMIT 6", v=vendor),
            "overdue": rows("SELECT obligation_id, title, obligation, due_date, days_left FROM v_obligations WHERE vendor=:v AND status='overdue' AND contract_status <> 'draft' ORDER BY due_date", v=vendor),
            "breaches": rows("SELECT title, metric_key, period, actual, target FROM v_sla WHERE vendor=:v AND breach ORDER BY period DESC LIMIT 6", v=vendor)}


class Weight(BaseModel):
    key: str
    weight: float
    enabled: bool = True


@router.put("/admin/risk-weights")
def weights_put(ws: list[Weight]):
    with SessionLocal() as s:
        for w in ws:
            if w.weight < 0 or w.weight > 100:
                raise HTTPException(422, "weights are 0-100")
            s.execute(text("UPDATE risk_weights SET weight=:w, enabled=:e WHERE key=:k"), {"w": w.weight, "e": w.enabled, "k": w.key})
        s.commit()
    _refresh()
    return risk_vendors()


@router.post("/risk/recompute")
def risk_recompute():
    return feeds.recompute()


# ------------------------------------------------------------------ benchmarks
BENCH = ["payment_terms_days", "liability_cap_multiple", "sla_availability_pct", "insurance_cover_usd", "warranty_days", "tfc_notice_days", "renewal_notice_days", "incident_notice_hours", "confidentiality_years", "acceptance_days"]


def _q(vals: list[float], p: float) -> float:
    vals = sorted(vals)
    k = (len(vals) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)


@router.get("/benchmarks")
def benchmarks():
    out = []
    mets = {m["key"]: m for m in rows("SELECT key, name, unit FROM metrics")}
    pol = rows("SELECT metric_key, name, operator, threshold, severity FROM checklist_rules WHERE rule_type='metric_threshold' AND enabled")
    for key in BENCH:
        if key not in mets:
            continue
        if key == "payment_terms_days":      # the effective value: amendments already applied
            vals = rows("""SELECT contract_id, title, vendor, type, payment_terms_days::float AS value FROM v_effective_terms WHERE status <> 'draft' AND payment_terms_days IS NOT NULL ORDER BY 5, vendor""")
        else:
            vals = rows("""SELECT contract_id, title, vendor, type, value_num AS value FROM v_values WHERE metric_key=:k AND status <> 'draft' AND type <> 'Amendment' AND value_num IS NOT NULL ORDER BY value_num, vendor""", k=key)
        if len(vals) < 2:
            continue
        xs = [float(v["value"]) for v in vals]
        q1, q3 = _q(xs, .25), _q(xs, .75)
        med = statistics.median(xs)
        policy = [{"name": p["name"], "operator": p["operator"], "threshold": float(p["threshold"]), "severity": p["severity"]} for p in pol if p["metric_key"] == key and p["threshold"] is not None]

        def fails(v: float) -> bool:
            return any((p["operator"] == ">=" and v < p["threshold"]) or (p["operator"] == "<=" and v > p["threshold"]) for p in policy)

        for v in vals:
            x = float(v["value"])
            v["value"] = x
            v["outlier"] = bool(q3 > q1 and (x < q1 - 1.5 * (q3 - q1) or x > q3 + 1.5 * (q3 - q1)))
            v["breaches_policy"] = fails(x)
            v["vs_median"] = round((x - med) / med, 3) if med else None
        by_vendor: dict[str, list[float]] = {}
        for v in vals:
            by_vendor.setdefault(v["vendor"], []).append(v["value"])
        out.append({"metric_key": key, "metric": mets[key]["name"], "unit": mets[key]["unit"], "n": len(xs), "min": min(xs), "p25": q1, "median": med, "p75": q3, "max": max(xs),
                    "policy": policy, "values": vals, "breaching": sum(1 for v in vals if v["breaches_policy"]),
                    "vendors": sorted(({"vendor": k, "median": statistics.median(v), "n": len(v)} for k, v in by_vendor.items()), key=lambda r: r["median"])})
    law = rows("SELECT governing_law, count(*) AS n FROM v_effective_terms WHERE status <> 'draft' AND governing_law IS NOT NULL GROUP BY 1 ORDER BY n DESC")
    caps = rows("""SELECT CASE WHEN liability_uncapped THEN 'Unlimited' WHEN liability_cap_multiple IS NOT NULL THEN liability_cap_multiple::text || 'x fees' ELSE 'Not stated / via MSA' END AS cap, count(*) AS n
                   FROM v_effective_terms WHERE status <> 'draft' GROUP BY 1 ORDER BY n DESC""")
    return {"metrics": out, "governing_law": law, "liability_caps": caps}
