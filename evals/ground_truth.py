"""Expected answers computed from labels.json + manifest.json only (never from the DB)."""

import json
from collections import defaultdict
from datetime import date, timedelta

from app.config import data_path

OVERRIDABLE = [
    "expiry_date",
    "notice_period_days",
    "auto_renew",
    "annual_value",
    "total_value",
    "payment_terms_days",
    "liability_cap_multiple",
    "liability_cap_text",
    "termination_for_convenience",
    "governing_law",
]


def load():
    labels = json.loads((data_path() / "labels.json").read_text())
    man = json.loads((data_path() / "manifest.json").read_text())["contracts"]
    seed = date.fromisoformat(labels["seed_date"])
    eff = {}
    meta = {m["key"]: m for m in man}
    for m in man:
        if m["type"] != "Amendment":
            eff[m["key"]] = {**labels["contracts"][m["key"]], **m, "_src": {}}
    for m in sorted(
        (m for m in man if m["type"] == "Amendment"),
        key=lambda m: labels["contracts"][m["key"]]["effective_date"],
    ):
        for f in OVERRIDABLE:
            if f in labels["contracts"][m["key"]]:
                eff[m["parent"]][f] = labels["contracts"][m["key"]][f]
                eff[m["parent"]]["_src"][f] = m["title"]
    return seed, eff, meta


def _d(s):
    return date.fromisoformat(s)


def _notice_dl(c):
    return _d(c["expiry_date"]) - timedelta(days=c["notice_period_days"] or 0)


def notice_60(today=None):
    seed, eff, _ = load()
    return {c["title"] for c in eff.values() if 0 <= (_notice_dl(c) - seed).days <= 60}


def expire_30():
    seed, eff, _ = load()
    return {c["title"] for c in eff.values() if 0 <= (_d(c["expiry_date"]) - seed).days <= 30}


def quarter_by_category():
    seed, eff, _ = load()
    q0 = date(seed.year, 3 * ((seed.month - 1) // 3) + 1, 1)
    q1 = date(q0.year + (q0.month == 10), (q0.month + 3 - 1) % 12 + 1, 1)
    out = defaultdict(float)
    for c in eff.values():
        if q0 <= _d(c["expiry_date"]) < q1:
            out[c["category"]] += c["annual_value"] or 0
    return dict(out)


def uncapped():
    return {c["vendor"] for c in load()[1].values() if c["liability_cap_text"] == "Unlimited"}


def saas_no_dpa():
    return {
        c["vendor"]
        for c in load()[1].values()
        if c["type"] == "SaaS" and c["processes_personal_data"] and not c["has_dpa"]
    }


def no_tfc():
    return {c["title"] for c in load()[1].values() if c["termination_for_convenience"] is False}


def bluepeak_payment():
    return next(
        c["payment_terms_days"]
        for c in load()[1].values()
        if c["type"] == "MSA" and "Bluepeak" in c["vendor"]
    )


def top5_vendors():
    tot = defaultdict(float)
    for c in load()[1].values():
        tot[c["vendor"]] += c["annual_value"] or 0
    return set(sorted(tot, key=tot.get, reverse=True)[:5])


def nda_before_msa():
    _, eff, meta = load()
    out = set()
    for k, c in eff.items():
        if (
            c["type"] == "NDA"
            and c.get("parent")
            and c["expiry_date"] < eff[c["parent"]]["expiry_date"]
        ):
            out.add(c["title"])
    return out


def auto_renewals():
    return {c["title"] for c in load()[1].values() if c["auto_renew"]}


def total_value():
    return sum(c["annual_value"] or 0 for c in load()[1].values())


def short_confidentiality():
    _, eff, _ = load()
    return {
        c["title"]
        for k, c in eff.items()
        if any(d["clause_type"] == "confidentiality" for d in c["deviations"])
    }


def vendor_owns_ip():
    return {
        c["title"]
        for c in load()[1].values()
        if any(d["clause_type"] == "ip_ownership" for d in c["deviations"])
    }


def non_indian_law():
    return {c["title"] for c in load()[1].values() if c["governing_law"] not in (None, "India")}


def uncapped_autorenew():
    return {
        c["title"]
        for c in load()[1].values()
        if c["liability_cap_text"] == "Unlimited" and c["auto_renew"]
    }


def _quarter(off):
    seed = load()[0]
    m = 3 * ((seed.month - 1) // 3) + 1 + 3 * off
    y, m = seed.year + (m - 1) // 12, (m - 1) % 12 + 1
    a = date(y, m, 1)
    b = date(y + (m + 2) // 12, (m + 2) % 12 + 1, 1)
    return a, b  # [a, b)


def next_quarter_titles():
    _, eff, _ = load()
    a, b = _quarter(1)
    return {c["title"] for c in eff.values() if a <= _d(c["expiry_date"]) < b}


def next_quarter_count():
    return len(next_quarter_titles())


def expire_90_by_category():
    seed, eff, _ = load()
    out = defaultdict(int)
    for c in eff.values():
        if 0 <= (_d(c["expiry_date"]) - seed).days <= 90:
            out[c["category"]] += 1
    return dict(out)


def autorenew_count():
    return len(auto_renewals())


def autorenew_value():
    return sum(c["annual_value"] or 0 for c in load()[1].values() if c["auto_renew"])


def contracts_per_vendor():
    out = defaultdict(int)
    for c in load()[1].values():
        out[c["vendor"]] += 1
    return dict(out)


def saas_total():
    return sum(c["annual_value"] or 0 for c in load()[1].values() if c["type"] == "SaaS")


def nda_this_year_count():
    seed, eff, _ = load()
    return sum(
        1 for c in eff.values() if c["type"] == "NDA" and _d(c["expiry_date"]).year == seed.year
    )
