"""What happens on site at a property: service calls against the response times the contracts promise, supplier contacts, and the property manager's page.

Promised response time = the "within N hours" the vendor's contract states (read from the clause that the 'Fault response time' value came from, on the
contract that applies at the property or its master agreement). A clause can promise two times ("attend a passenger entrapment within 1 hour, and any other
fault within 4 hours"): an emergency is held to the shortest, any other call to the longest. Planned work has no promise.
Calls and contacts come from people (the API) or from files in the feeds folder (`service_log.csv`, `vendor_contacts.csv`)."""
from __future__ import annotations

import csv
import re
import statistics
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import text

from app import scope
from app.config import data_path

FEED_FILES = ("service_log.csv", "vendor_contacts.csv")


def _rows(s, sql: str, **p) -> list[dict]:
    return [dict(r) for r in s.execute(text(sql), p).mappings()]


def promises(s, prop: str) -> dict[str, dict]:
    """vendor -> {contract_id, title, emergency_hours, fault_hours, text, page} for the vendors that apply at the property."""
    out: dict[str, dict] = {}
    ids = scope.contract_ids(s, prop)
    for r in _rows(s, """SELECT c.id, c.title, c.vendor, c.property, cl.text, cl.page, ev.value_num
                         FROM extracted_values ev JOIN contracts c ON c.id = ev.contract_id LEFT JOIN clauses cl ON cl.id = ev.clause_id
                         WHERE ev.metric_key = 'response_time_hours' AND c.id = ANY(:ids) AND c.status <> 'draft'
                         ORDER BY (c.property = :p) DESC NULLS LAST, c.id""", ids=ids, p=prop):
        if r["vendor"] in out:
            continue                                   # the contract naming the property wins over the master agreement
        if not re.search(r"\b(?:attend\w*|respond\w*|response|repair\w*|restor\w*|replace\w*|replacement|visit\w*|on site|turnaround|returned|call-?out)\b", r["text"] or "", re.I):
            continue                                   # 'within 24 hours' of a product recall or an availability report is not a service response time
        hours = sorted({float(h) for h in re.findall(r"within\s+(?:[a-z\-]+\s*)?\(?(\d+(?:\.\d+)?)\)?\s*hours?", r["text"] or "", re.I) if float(h) <= 72}) or [float(r["value_num"])]
        out[r["vendor"]] = dict(contract_id=r["id"], title=r["title"], emergency_hours=hours[0], fault_hours=hours[-1], text=(r["text"] or "")[:300], page=r["page"])
    return out


def _hours(a, b) -> float | None:
    return round((b - a).total_seconds() / 3600, 1) if a and b else None


def service(s, prop: str, days: int = 90) -> dict:
    """Calls at the property in the last `days`, each against its promise, and a line per vendor."""
    prom = promises(s, prop)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    calls = _rows(s, """SELECT id, vendor, contract_id, kind, description, reported_at, attended_at, resolved_at, reported_by, source
                        FROM service_events WHERE property = :p AND reported_at >= :d ORDER BY reported_at DESC""", p=prop, d=since)
    now = datetime.now(timezone.utc)
    for c in calls:
        p = prom.get(c["vendor"])
        c["promised_hours"] = None if c["kind"] == "planned" or not p else (p["emergency_hours"] if c["kind"] == "emergency" else p["fault_hours"])
        c["attend_hours"] = _hours(c["reported_at"], c["attended_at"])
        waited = c["attend_hours"] if c["attend_hours"] is not None else _hours(c["reported_at"], now)
        c["open"] = c["resolved_at"] is None
        c["late"] = bool(c["promised_hours"] is not None and waited is not None and waited > c["promised_hours"])
        c["contract_id"] = c["contract_id"] or (p or {}).get("contract_id")
    vend = []
    for v in sorted({c["vendor"] for c in calls} | set(prom)):
        cs = [c for c in calls if c["vendor"] == v and c["promised_hours"] is not None]
        att = [c["attend_hours"] for c in cs if c["attend_hours"] is not None]
        vend.append(dict(vendor=v, promise=prom.get(v), calls=len([c for c in calls if c["vendor"] == v]), measured=len(cs), late=sum(c["late"] for c in cs),
                         on_time_pct=round(100 * (1 - sum(c["late"] for c in cs) / len(cs))) if cs else None,
                         median_hours=round(statistics.median(att), 1) if att else None, worst_hours=max(att) if att else None,
                         open=sum(c["open"] for c in calls if c["vendor"] == v)))
    vend.sort(key=lambda x: (-(x["late"] or 0), -(x["calls"] or 0), x["vendor"]))
    return {"calls": calls, "vendors": vend, "days": days, "late": sum(c["late"] for c in calls), "open": sum(c["open"] for c in calls)}


def contacts(s, prop: str | None = None, vendor: str | None = None) -> list[dict]:
    """Contacts for the vendors at a property: the property's own contact first, then the vendor's group-wide one."""
    vs = scope.vendors(s, prop) if prop else None
    return _rows(s, """SELECT id, vendor, property, name, role, phone, email, note, source FROM vendor_contacts
                       WHERE (CAST(:v AS text) IS NULL OR vendor = :v) AND (CAST(:p AS text) IS NULL OR property IS NULL OR property = :p)
                         AND (CAST(:vs AS text[]) IS NULL OR vendor = ANY(:vs))
                       ORDER BY vendor, (property IS NULL), name""", v=vendor, p=prop, vs=vs)


def load_files(s) -> dict:
    """Read service_log.csv and vendor_contacts.csv from the feeds folder (idempotent: a service call is keyed by its external id; file contacts are replaced)."""
    root = data_path() / "feeds"
    n = dict(calls=0, contacts=0)
    f = root / "service_log.csv"
    if f.exists():
        with f.open(newline="") as fh:
            for r in csv.DictReader(fh):
                s.execute(text("""INSERT INTO service_events (property, vendor, kind, description, reported_at, attended_at, resolved_at, reported_by, source, external_id)
                                  VALUES (:p, :v, :k, :d, :ra, :aa, :rs, :by, 'file', :x)
                                  ON CONFLICT (external_id) DO UPDATE SET attended_at = EXCLUDED.attended_at, resolved_at = EXCLUDED.resolved_at, description = EXCLUDED.description"""),
                          {"p": r["property"], "v": r["vendor"], "k": r.get("kind") or "fault", "d": r.get("description"), "ra": r["reported_at"],
                           "aa": r.get("attended_at") or None, "rs": r.get("resolved_at") or None, "by": r.get("reported_by") or None, "x": r.get("id") or None})
                n["calls"] += 1
    f = root / "vendor_contacts.csv"
    if f.exists():
        s.execute(text("DELETE FROM vendor_contacts WHERE source = 'file'"))
        with f.open(newline="") as fh:
            for r in csv.DictReader(fh):
                s.execute(text("""INSERT INTO vendor_contacts (vendor, property, name, role, phone, email, note, source) VALUES (:v, :p, :n, :r, :ph, :e, :no, 'file')"""),
                          {"v": r["vendor"], "p": r.get("property") or None, "n": r["name"], "r": r.get("role") or None, "ph": r.get("phone") or None,
                           "e": r.get("email") or None, "no": r.get("note") or None})
                n["contacts"] += 1
    return n


def my_property(s, prop: str, today: date | None = None) -> dict | None:
    """Everything the manager of one property acts on, in one answer."""
    from app import certificates, properties

    today = today or date.today()
    pr = _rows(s, "SELECT id, name, city, country, kind, rooms FROM properties WHERE name = :p", p=prop)
    if not pr:
        return None
    ids = scope.contract_ids(s, prop)
    vendors = scope.vendors(s, prop)
    ov = next((p for p in properties.overview(s)["properties"] if p["property"] == prop), {})
    ren = _rows(s, """SELECT contract_id AS id, title, vendor, type, annual_value, auto_renew, expiry_date, notice_deadline, days_left, notice_days_left,
                             (SELECT property FROM contracts c WHERE c.id = contract_id) AS property
                      FROM v_renewals WHERE contract_id = ANY(:ids) AND days_left >= 0
                        AND (days_left <= 120 OR (auto_renew AND notice_days_left <= 60)) ORDER BY LEAST(COALESCE(notice_days_left, days_left), days_left)""", ids=ids)
    obl = _rows(s, """SELECT obligation_id AS id, contract_id, title AS contract, vendor, kind, party, obligation, due_date, status, days_left
                      FROM v_obligations WHERE contract_id = ANY(:ids) AND contract_status <> 'draft'
                        AND (status = 'overdue' OR (status = 'open' AND days_left BETWEEN 0 AND 30)) ORDER BY due_date""", ids=ids)
    certs = [c for c in certificates.listing(s, today)["certificates"] if c["vendor"] in vendors]
    svc = service(s, prop)
    alerts = _rows(s, """SELECT id, title, severity, link, created_at FROM alerts WHERE status = 'open' AND (:p = ANY(properties) OR properties = '{}')
                         ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, created_at DESC LIMIT 20""", p=prop)
    sale = properties.detail(s, pr[0]["id"])["sale"]
    act = []        # one list, most urgent first: what to do this week
    for r in ren:
        nd = r["notice_days_left"] if r["auto_renew"] else None
        if nd is not None and nd < 0:
            act.append(dict(kind="renewal", severity="critical", title=f"Notice deadline passed {-nd} days ago: {r['vendor']}", detail=f"{r['title']} renews automatically on {r['expiry_date']:%b %d, %Y}.", link=f"/contracts/{r['id']}", days=nd))
        elif nd is not None and nd <= 30:
            act.append(dict(kind="renewal", severity="high", title=f"Decide on renewal in {nd} days: {r['vendor']}", detail=f"Last day to give notice {r['notice_deadline']:%b %d, %Y}.", link=f"/contracts/{r['id']}", days=nd))
        elif r["days_left"] <= 60:
            act.append(dict(kind="renewal", severity="medium", title=f"Ends in {r['days_left']} days: {r['vendor']}", detail=r["title"], link=f"/contracts/{r['id']}", days=r["days_left"]))
    for o in obl:
        if o["kind"] == "renewal":
            continue                                  # the renewal itself is already on the list, with its deadline
        act.append(dict(kind="obligation", severity="high" if o["status"] == "overdue" else "medium", title=("Overdue: " if o["status"] == "overdue" else f"Due in {o['days_left']} days: ") + o["obligation"],
                        detail=f"{o['vendor']} · {o['party']} owes it", link="/obligations", days=o["days_left"] if o["days_left"] is not None else -999))
    for c in certs:
        if c["status"] in ("expired", "expiring"):
            act.append(dict(kind="certificate", severity="critical" if c["status"] == "expired" else "high",
                            title=f"{c['name']} {'expired' if c['status'] == 'expired' else 'expires'} {'' if c['days_left'] >= 0 else str(-c['days_left']) + ' days ago'}{'in ' + str(c['days_left']) + ' days' if c['days_left'] >= 0 else ''}: {c['vendor']}".replace("  ", " "),
                            detail="Ask the vendor for the renewed certificate.", link="/certificates", days=c["days_left"]))
    for c in svc["calls"]:
        if c["late"] and (c["open"] or c["reported_at"] >= datetime.now(timezone.utc) - timedelta(days=14)):
            act.append(dict(kind="service", severity="high", title=f"Late {'and still open' if c['open'] else 'response'}: {c['vendor']}",
                            detail=f"{c['description'] or c['kind']} · promised {c['promised_hours']:g} h, {'waiting' if c['attend_hours'] is None else 'attended after ' + format(c['attend_hours'], 'g') + ' h'}",
                            link="#service", days=0))
    sev = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    act.sort(key=lambda a: (sev[a["severity"]], a["days"]))
    return {**pr[0], "property": prop, "annual_value": ov.get("annual_value"), "value_per_room": ov.get("value_per_room"), "contracts": len(ids), "vendors": vendors,
            "act": act, "renewals": ren, "obligations": obl, "certificates": certs, "service": svc, "contacts": contacts(s, prop), "alerts": alerts, "sale": sale}
