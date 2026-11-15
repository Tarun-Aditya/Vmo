"""Expected answers for the pilot corpus, computed from data/labels_pilot.json only (the spec the documents were written from; never from the DB)."""
import json
from datetime import date, timedelta

from app.config import data_path

OVERRIDABLE = ["expiry_date", "notice_period_days", "auto_renew", "annual_value", "total_value", "payment_terms_days", "liability_cap_multiple", "liability_cap_text",
               "termination_for_convenience", "governing_law"]


def _d(s):
    return date.fromisoformat(s) if s else None


def load():
    import os

    lab = json.loads((data_path() / os.environ.get("LABELS", "labels_pilot.json")).read_text())      # LABELS=labels_hotel.json for the hotel corpus
    today = date.fromisoformat(lab["seed_date"])
    eff = {k: {**v, **v["meta"]} for k, v in lab["contracts"].items() if v["meta"]["type"] != "Amendment"}
    for k, v in sorted(((k, v) for k, v in lab["contracts"].items() if v["meta"]["type"] == "Amendment"), key=lambda kv: kv[1]["effective_date"]):
        for f in OVERRIDABLE:
            if f in v:
                eff[v["meta"]["parent"]][f] = v[f]
    return today, [c for c in eff.values() if c["status"] != "draft"]


def uncapped():
    return {c["vendor"] for _, cs in [load()] for c in cs if c.get("liability_cap_multiple") is None and "unlimited" in (c.get("liability_cap_text") or "").lower()}


def saas_no_dpa():
    return {c["vendor"] for _, cs in [load()] for c in cs if c["type"] == "SaaS" and c["processes_personal_data"] and not c["has_dpa"]}


def no_tfc():
    return {c["vendor"] for _, cs in [load()] for c in cs if c.get("termination_for_convenience") is False}


def auto_renewals():
    return {c["vendor"] for _, cs in [load()] for c in cs if c.get("auto_renew")}


def expire_90():
    t, cs = load()
    return {c["vendor"] for c in cs if _d(c["expiry_date"]) and t <= _d(c["expiry_date"]) <= t + timedelta(days=90)}


def total_value():
    t, cs = load()
    return sum(float(c["annual_value"] or 0) for c in cs if _d(c["expiry_date"]) and _d(c["expiry_date"]) >= t)


def top5_vendors():
    t, cs = load()
    tot: dict[str, float] = {}
    for c in cs:
        if c["annual_value"] and _d(c["expiry_date"]) >= t:
            tot[c["vendor"]] = tot.get(c["vendor"], 0) + float(c["annual_value"])
    return set(sorted(tot, key=tot.get, reverse=True)[:5])


def non_ny_law():
    return {c["vendor"] for _, cs in [load()] for c in cs if c.get("governing_law") and "new york" not in c["governing_law"].lower()}


# ---------------------------------------------------------------- hotel corpus (LABELS=labels_hotel.json): the owner's questions
def _at(name):
    return [c for _, cs in [load()] for c in cs if (c.get("property") or "").endswith(name)]


def harbor_vendors():
    return {c["vendor"] for c in _at("Harbor Hotel")}


def lakeside_count():
    return len(_at("Lakeside Resort"))


def property_counts():
    out: dict[str, float] = {}
    for _, cs in [load()]:
        for c in cs:
            if c.get("property"):
                out[c["property"]] = out.get(c["property"], 0) + 1
    return out


def laundry_rates():
    return {c["vendor"] + "|" + c["property"]: c["values"]["laundry_rate_per_kg"] for _, cs in [load()] for c in cs if (c.get("values") or {}).get("laundry_rate_per_kg")}


def laundry_rate_values():
    """The per-kilogram rates the hotel spec writes into the executed laundry schedules (the labels hold no rates; the spec's facts do)."""
    import re

    from app.docgen import hotel_spec

    return {float(m.group(1)) for d in hotel_spec.DOCS if d.get("status") != "draft" for e in d.get("extras") or [] for m in [re.search(r"USD ([\d.]+) per kilogram", e)] if m}


def notice_passed():
    t, cs = load()
    return {c["vendor"] for c in cs if c.get("auto_renew") and c.get("notice_period_days") and _d(c["expiry_date"]) and _d(c["expiry_date"]) >= t
            and _d(c["expiry_date"]) - timedelta(days=int(c["notice_period_days"])) < t}


def personal_data_no_dpa_vendors():
    return {c["vendor"] for _, cs in [load()] for c in cs if c["processes_personal_data"] and not c["has_dpa"] and c["type"] not in ("DPA", "NDA")}


def harbor_vendors_incl_group():
    """Vendors whose contracts apply at Harbor Hotel: the ones naming it, plus group agreements covering it (a group agreement with schedules covers the
    properties its schedules name; one without schedules covers every property). NDAs, DPAs and amendments are not service contracts."""
    _, cs = load()
    named = {c["vendor"] for c in cs if (c.get("property") or "").endswith("Harbor Hotel")}
    for g in cs:
        if g.get("property") or g["type"] in ("NDA", "DPA", "Amendment"):
            continue
        kids = [c for c in cs if c.get("parent") == g["key"] and c.get("property")]
        if not kids or any((c["property"] or "").endswith("Harbor Hotel") for c in kids):
            named.add(g["vendor"])
    return named
