"""Vendor risk scorecards: five explainable components (0-100 each, higher = riskier) combined with admin-set weights."""
from __future__ import annotations

import json
import math
from datetime import date, timedelta

from sqlalchemy import text

TIERS = [(50, "critical"), (30, "high"), (15, "medium"), (0, "low")]


def sat(x: float, k: float) -> float:
    """Diminishing returns: 0 -> 0, k -> 63, 3k -> 95."""
    return round(100 * (1 - math.exp(-max(x, 0) / k)), 1)


def tier(score: float) -> str:
    return next(t for lim, t in TIERS if score >= lim)


def compute_all(s, today: date | None = None) -> int:
    today = today or date.today()
    weights = {r["key"]: float(r["weight"]) for r in s.execute(text("SELECT key, weight FROM risk_weights WHERE enabled")).mappings()}
    vendors = [r[0] for r in s.execute(text("SELECT DISTINCT vendor FROM contracts WHERE status <> 'draft' ORDER BY 1"))]
    total_value = float(s.execute(text("SELECT COALESCE(sum(annual_value),0) FROM v_effective_terms WHERE status <> 'draft'")).scalar() or 0)
    s.execute(text("DELETE FROM vendor_scores"))
    for v in vendors:
        comp: dict[str, dict] = {}
        # ---- contract terms
        pts, drivers = 0.0, []
        for r in s.execute(text("""SELECT t.contract_id, t.title, t.type, t.liability_uncapped, t.termination_for_convenience, t.processes_personal_data, t.has_dpa, t.fully_executed
                                   FROM v_effective_terms t WHERE t.vendor=:v AND t.status <> 'draft'"""), {"v": v}).mappings():
            if r["liability_uncapped"]:
                pts += 30
                drivers.append(f"Uncapped liability: {r['title']}")
            if r["termination_for_convenience"] is False and r["type"] in ("MSA", "SaaS"):
                pts += 8
                drivers.append(f"No termination for convenience: {r['title']}")
            if r["processes_personal_data"] and not r["has_dpa"]:
                pts += 25
                drivers.append(f"Personal data without a DPA: {r['title']}")
            if r["fully_executed"] is False:
                pts += 25
                drivers.append(f"Not fully signed: {r['title']}")
        wsev = {"critical": 12, "high": 6, "medium": 2, "low": 0.5}
        fails = s.execute(text("""SELECT cr.severity, count(*) FROM check_results cr JOIN contracts c ON c.id = cr.contract_id
                                  WHERE c.vendor=:v AND c.status <> 'draft' AND cr.status='fail' AND cr.rule_key NOT IN ('executed','no_unlimited_liability')
                                  GROUP BY 1"""), {"v": v}).all()
        for sev, n in fails:
            pts += wsev[sev] * n
        nf = sum(n for _, n in fails)
        if nf:
            drivers.append(f"{nf} checklist rule failure{'s' if nf != 1 else ''} across active contracts")
        comp["contract_risk"] = {"score": sat(pts, 60), "drivers": drivers[:6]}
        # ---- renewal exposure
        pts, drivers = 0.0, []
        for r in s.execute(text("SELECT title, auto_renew, expiry_date, notice_deadline, notice_days_left, days_left, annual_value FROM v_renewals WHERE vendor=:v"), {"v": v}).mappings():
            if r["auto_renew"] and r["notice_days_left"] is not None and r["notice_days_left"] < 0 and r["days_left"] >= 0:
                pts += 50
                drivers.append(f"Auto-renewal notice deadline passed: {r['title']}")
            elif r["auto_renew"] and r["notice_days_left"] is not None and r["notice_days_left"] <= 30:
                pts += 30
                drivers.append(f"Auto-renewal notice due within {max(r['notice_days_left'], 0)} days: {r['title']}")
            elif r["days_left"] is not None and 0 <= r["days_left"] <= 90:
                pts += 12
                drivers.append(f"Expires in {r['days_left']} days: {r['title']}")
        comp["renewal_exposure"] = {"score": sat(pts, 60), "drivers": drivers[:6]}
        # ---- performance
        pts, drivers = 0.0, []
        for r in s.execute(text("""SELECT title, period, actual, target, shortfall, metric_key FROM v_sla WHERE vendor=:v AND breach AND period >= :since ORDER BY period"""),
                           {"v": v, "since": today - timedelta(days=183)}).mappings():
            pts += 12 + min(float(r["shortfall"] or 0) * 40, 18)
            drivers.append(f"SLA breach {r['period']:%b %Y}: {float(r['actual']):g} vs {float(r['target']):g} ({r['title']})")
        od = s.execute(text("SELECT title, obligation, kind FROM v_obligations WHERE vendor=:v AND status='overdue' AND contract_status <> 'draft' AND party <> 'Customer'"), {"v": v}).all()
        for t, o, k in od:
            pts += 15 if k == "milestone" else 8
            drivers.append(f"Overdue: {o} ({t})")
        comp["performance"] = {"score": sat(pts, 50), "drivers": drivers[:6]}
        # ---- spend compliance
        pts, drivers = 0.0, []
        wx = {"critical": 40, "high": 25, "medium": 10, "low": 3}
        for sev, n, amt in s.execute(text("SELECT severity, count(*), sum(amount_at_risk) FROM spend_exceptions WHERE vendor=:v GROUP BY 1"), {"v": v}):
            pts += wx[sev] * n
            drivers.append(f"{n} {sev} spend exception{'s' if n != 1 else ''} (${float(amt):,.0f} at risk)")
        comp["spend_compliance"] = {"score": sat(pts, 70), "drivers": drivers[:6]}
        # ---- concentration
        val = float(s.execute(text("SELECT COALESCE(sum(annual_value),0) FROM v_effective_terms WHERE vendor=:v AND status <> 'draft'"), {"v": v}).scalar() or 0)
        share = val / total_value if total_value else 0
        comp["concentration"] = {"score": round(min(100, max(0, (share - 0.10) / 0.30 * 100)), 1), "share": round(share, 4),
                                 "drivers": [f"{share:.0%} of annual portfolio value (${val:,.0f})"] if share >= 0.10 else []}
        wsum = sum(weights.get(k, 0) for k in comp) or 1
        score = round(sum(comp[k]["score"] * weights.get(k, 0) for k in comp) / wsum, 1)
        s.execute(text("INSERT INTO vendor_scores (vendor, score, tier, components) VALUES (:v,:s,:t,CAST(:c AS jsonb))"),
                  {"v": v, "s": score, "t": tier(score), "c": json.dumps(comp)})
    return len(vendors)
