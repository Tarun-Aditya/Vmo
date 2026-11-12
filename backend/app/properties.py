"""Properties (hotels / sites) as records, and what is contracted at each.

A property comes into being when a document names it; its attributes (rooms, city, kind) come from `properties.json` in the data folder or from a person
(PATCH /api/properties/{id}). Group-level agreements are attributed to the properties they cover (view v_property_contracts), so a property's yearly cost
includes its share of the energy contract or the booking system, not only the schedules that name it."""
from __future__ import annotations

import json

from sqlalchemy import text

from app.config import data_path

ATTRS = ("city", "country", "kind", "rooms", "opened_year")


def sync(s) -> int:
    """Create a record for every property named by a contract and fill empty attributes from properties.json. Never overwrites a person's edit."""
    s.execute(text("INSERT INTO properties (name) SELECT DISTINCT property FROM contracts WHERE property IS NOT NULL ON CONFLICT (name) DO NOTHING"))
    f = data_path() / "properties.json"
    if f.exists():
        for p in json.loads(f.read_text()):
            s.execute(text("INSERT INTO properties (name) VALUES (:n) ON CONFLICT (name) DO NOTHING"), {"n": p["name"]})
            for a in ATTRS:
                if p.get(a) is not None:
                    s.execute(text(f"UPDATE properties SET {a} = :v WHERE name = :n AND {a} IS NULL"), {"v": p[a], "n": p["name"]})
    return s.execute(text("SELECT count(*) FROM properties")).scalar()


def _rows(s, sql: str, **p) -> list[dict]:
    return [dict(r) for r in s.execute(text(sql), p).mappings()]


def overview(s) -> dict:
    props = _rows(s, """
        SELECT p.id, p.name AS property, p.city, p.country, p.kind, p.rooms,
               count(v.contract_id) AS contracts, count(v.contract_id) FILTER (WHERE v.basis = 'named') AS named_contracts,
               count(DISTINCT v.vendor) AS vendors,
               COALESCE(sum(v.contract_annual_value * v.share), 0) AS annual_value,
               COALESCE(sum(v.contract_annual_value) FILTER (WHERE v.basis = 'named'), 0) AS direct_value,
               COALESCE(sum(v.contract_annual_value * v.share) FILTER (WHERE v.basis <> 'named'), 0) AS shared_value,
               count(*) FILTER (WHERE v.expiry_date BETWEEN current_date AND current_date + 90) AS ending_90,
               COALESCE(array_agg(DISTINCT v.category) FILTER (WHERE v.category IS NOT NULL), '{}') AS categories,
               COALESCE(array_agg(DISTINCT v.vendor) FILTER (WHERE v.vendor IS NOT NULL), '{}') AS vendor_names
        FROM properties p LEFT JOIN v_property_contracts v ON v.property_id = p.id GROUP BY p.id ORDER BY p.name""")
    for p in props:
        p["value_per_room"] = round(float(p["annual_value"]) / p["rooms"], 2) if p["rooms"] else None
    grp = s.execute(text("SELECT count(*) FROM contracts WHERE property IS NULL AND status <> 'draft' AND type NOT IN ('Amendment','NDA','DPA')")).scalar()
    return {"properties": props, "group_level": grp, "rooms_known": all(p["rooms"] for p in props) if props else False}


def detail(s, pid: int) -> dict | None:
    p = _rows(s, "SELECT id, name AS property, city, country, kind, rooms, opened_year FROM properties WHERE id = :i", i=pid)
    if not p:
        return None
    items = _rows(s, """SELECT contract_id, title, vendor, category, type, expiry_date, basis, contract_annual_value, share,
                               contract_annual_value * share AS attributed_value FROM v_property_contracts WHERE property_id = :i
                        ORDER BY contract_annual_value * share DESC NULLS LAST, vendor""", i=pid)
    return {**p[0], "contracts": items}


# Values where a lower number is the better deal for the buyer, and those where higher is better. Everything else is shown without a verdict.
LOWER_BETTER = {"payment_terms_days": False, "renewal_notice_days": True, "response_time_hours": True, "commission_pct": True, "incident_notice_hours": True, "breach_notice_hours": True}


def compare(s) -> dict:
    """Where the same vendor serves several properties, or several vendors supply the same category: the terms side by side and the gap between best and worst."""
    rows = _rows(s, """
        SELECT c.id AS contract_id, c.title, c.vendor, c.category, c.property, p.rooms,
               COALESCE(e.annual_value, c.annual_value) AS annual_value, COALESCE(e.payment_terms_days, c.payment_terms_days) AS payment_terms_days,
               COALESCE(e.expiry_date, c.expiry_date) AS expiry_date
        FROM contracts c JOIN properties p ON p.name = c.property LEFT JOIN v_effective_terms e ON e.contract_id = c.id
        WHERE c.status <> 'draft' AND c.type NOT IN ('Amendment', 'NDA', 'DPA')""")
    vals = _rows(s, """SELECT ev.contract_id, ev.metric_key, m.name, m.unit, ev.value_num, ev.page FROM extracted_values ev JOIN metrics m ON m.key = ev.metric_key
                       WHERE ev.value_num IS NOT NULL AND m.enabled""")
    by_contract: dict[int, list[dict]] = {}
    for v in vals:
        by_contract.setdefault(v["contract_id"], []).append(v)

    def block(group_rows: list[dict], label: dict) -> dict | None:
        if len({r["property"] for r in group_rows}) < 2:
            return None
        measures: dict[str, dict] = {}
        for r in group_rows:
            if r["annual_value"] and r["rooms"]:
                measures.setdefault("value_per_room", dict(key="value_per_room", name="Yearly cost per room", unit="USD/room", lower_better=True, points=[]))["points"].append(
                    dict(property=r["property"], contract_id=r["contract_id"], vendor=r["vendor"], value=round(float(r["annual_value"]) / r["rooms"], 2), page=None))
            for v in by_contract.get(r["contract_id"], []):
                m = measures.setdefault(v["metric_key"], dict(key=v["metric_key"], name=v["name"], unit=v["unit"], points=[],
                                                              lower_better=True if v["unit"] and "/" in v["unit"] else LOWER_BETTER.get(v["metric_key"])))
                m["points"].append(dict(property=r["property"], contract_id=r["contract_id"], vendor=r["vendor"], value=float(v["value_num"]), page=v["page"]))
        out = []
        for m in measures.values():
            pts = m["points"]
            lo, hi = min(p["value"] for p in pts), max(p["value"] for p in pts)
            if len({p["property"] for p in pts}) < 2 or hi == lo or lo <= 0:
                continue
            m["spread_pct"] = round((hi - lo) / lo * 100, 1)
            m["best"] = (lo if m["lower_better"] else hi) if m["lower_better"] is not None else None
            # a unit rate: what the dearer properties would save at the best rate, assuming the same volume (yearly value x (1 - best / own rate))
            if m["lower_better"] and m["unit"] and "/" in m["unit"] and m["key"] != "value_per_room":
                av = {r["contract_id"]: float(r["annual_value"] or 0) for r in group_rows}
                m["saving_estimate"] = round(sum(av[p["contract_id"]] * (1 - lo / p["value"]) for p in pts), 0)
            m["points"] = sorted(pts, key=lambda p: p["value"])
            out.append(m)
        if not out:
            return None
        out.sort(key=lambda m: (-(m.get("saving_estimate") or 0), -m["spread_pct"]))
        return {**label, "properties": sorted({r["property"] for r in group_rows}), "measures": out, "saving_estimate": sum(m.get("saving_estimate") or 0 for m in out)}

    vend: dict[str, list[dict]] = {}
    cat: dict[str, list[dict]] = {}
    for r in rows:
        vend.setdefault(r["vendor"], []).append(r)
        cat.setdefault(r["category"], []).append(r)
    same_vendor = [b for v, g in sorted(vend.items()) if (b := block(g, {"vendor": v, "category": g[0]["category"]}))]
    done = {b["vendor"] for b in same_vendor}
    same_cat = [b for c, g in sorted(cat.items()) if len({r["vendor"] for r in g}) > 1 or not ({r["vendor"] for r in g} & done) if (b := block(g, {"category": c}))]
    same_vendor.sort(key=lambda b: -b["saving_estimate"])
    return {"same_vendor": same_vendor, "same_category": same_cat, "saving_estimate": sum(b["saving_estimate"] for b in same_vendor)}
