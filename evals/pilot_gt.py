"""Expected answers for the pilot corpus, computed from data/labels_pilot.json only (the spec the documents were written from; never from the DB)."""
import json
from datetime import date, timedelta

from app.config import data_path

OVERRIDABLE = ["expiry_date", "notice_period_days", "auto_renew", "annual_value", "total_value", "payment_terms_days", "liability_cap_multiple", "liability_cap_text",
               "termination_for_convenience", "governing_law"]


def _d(s):
    return date.fromisoformat(s) if s else None


def load():
    lab = json.loads((data_path() / "labels_pilot.json").read_text())
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
