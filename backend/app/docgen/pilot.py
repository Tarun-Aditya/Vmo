"""Pilot corpus: prompts for Claude to write each contract from its spec, labels computed from the spec, and the renderer that
turns the stored Markdown (with date tokens) into .md / .docx / .pdf files in the inbox at seed time."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

from app.docgen import pilot_spec
from app.docgen.pilot_spec import CUSTOMER, DOCS, STYLES

CORPUS_DIR = Path(__file__).resolve().parents[3] / "corpus" / "pilot"
PACK = {"name": "pilot", "customer": CUSTOMER, "customer_desc": "a retailer; US headquarters", "domain": "IT-services engagement", "docs": DOCS, "styles": STYLES,
        "dir": CORPUS_DIR, "labels": "labels_pilot.json", "manifest": "manifest_pilot.json"}


def use_pack(name: str) -> None:
    """Switch the generator to another corpus (e.g. 'hotel'): its customer, documents, styles and corpus folder."""
    global CUSTOMER, DOCS, STYLES, CORPUS_DIR
    if name == "hotel":
        from app.docgen import hotel_spec as hs

        PACK.update(name="hotel", customer=hs.CUSTOMER, customer_desc=hs.CUSTOMER_DESC, domain=hs.DOMAIN, docs=hs.DOCS, styles=hs.STYLES,
                    dir=Path(__file__).resolve().parents[3] / "corpus" / "hotel", labels="labels_hotel.json", manifest="manifest_hotel.json")
    else:
        PACK.update(name="pilot", customer=pilot_spec.CUSTOMER, customer_desc="a retailer; US headquarters", domain="IT-services engagement", docs=pilot_spec.DOCS, styles=pilot_spec.STYLES,
                    dir=Path(__file__).resolve().parents[3] / "corpus" / "pilot", labels="labels_pilot.json", manifest="manifest_pilot.json")
    CUSTOMER, DOCS, STYLES, CORPUS_DIR = PACK["customer"], PACK["docs"], PACK["styles"], PACK["dir"]
DATE_FMT = {"us_articles": "%B %d, %Y", "us_sections": "%B %d, %Y", "uk_numbered": "%d %B %Y", "plain": "%B %d, %Y", "schedule_heavy": "%d %B %Y", "short_form": "%d %B %Y", "vendor_paper": "%B %d, %Y", "sow_form": "%d %B %Y"}
SIGNERS = {"customer": [("Michael Brennan", "Chief Procurement Officer"), ("Helena Cruz", "VP Technology Sourcing")], "supplier": ["Richard Hale", "Anika Rao", "Daniel Okafor", "Sofia Marchetti", "Kenji Watanabe", "Grace Mbeki"]}


def add_months(d: date, n: int) -> date:
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    for day in (d.day, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def spec_by_key() -> dict[str, dict]:
    return {d["key"]: d for d in DOCS}


def dates(spec: dict, seed: date) -> dict[str, date]:
    eff = seed + timedelta(days=spec["eff"])
    out = {"EFFECTIVE": eff, "EXPIRY": add_months(eff, spec.get("term") or 12), "SIGNED_CUSTOMER": eff - timedelta(days=10), "SIGNED_SUPPLIER": eff - timedelta(days=7)}
    if spec["type"] == "Amendment":
        out["NEW_EXPIRY"] = add_months(seed + timedelta(days=spec_by_key()[spec["amends"]]["eff"]), spec["ov"].get("expiry_term_months", 36))
    if spec.get("parent"):
        out["PARENT_DATE"] = seed + timedelta(days=spec_by_key()[spec["parent"]]["eff"])
    if spec.get("amends"):
        out["PARENT_DATE"] = seed + timedelta(days=spec_by_key()[spec["amends"]]["eff"])
    for i, (_, off) in enumerate(spec.get("ms") or [], 1):
        out[f"MS{i}"] = seed + timedelta(days=off)
    return out


def signers(spec: dict) -> tuple[str, str]:
    n = sum(ord(c) for c in spec["key"])
    return SIGNERS["customer"][n % 2][0], SIGNERS["supplier"][n % len(SIGNERS["supplier"])]


def money(n) -> str:
    return f"{int(n):,}"


def facts(spec: dict) -> list[str]:
    t = spec["type"]
    f = [f"Document type: {t}" + (" (a vendor draft not yet signed)" if spec.get("status") == "draft" else ""), f"Customer: {CUSTOMER} ({PACK['customer_desc']})", f"Supplier / counterparty: {spec['vendor']}"]
    if spec.get("prop"):
        f.append(f"Property: the services are delivered at {spec['prop']} (state the property name in the agreement, in the parties or services section)")
    if spec.get("parent"):
        f.append(f"It is issued under the parent agreement ({spec_by_key()[spec['parent']]['type']}) dated {{{{PARENT_DATE}}}} between the same parties; refer to the parent by type and date")
    if spec.get("amends"):
        f.append(f"It amends the {spec_by_key()[spec['amends']]['type']} dated {{{{PARENT_DATE}}}} between the same parties. Amendment changes: payment terms become {spec['ov']['payment_terms_days']} days; the term is extended so that the agreement now expires on {{{{NEW_EXPIRY}}}}. Everything else is unchanged")
        f.append("Amendment effective date: {{EFFECTIVE}}")
        return f
    f.append("Effective date: {{EFFECTIVE}}; the initial term runs until {{EXPIRY}} (" + f"{spec.get('term')} months)")
    if spec.get("annual"):
        f.append(f"Annual fees: USD {money(spec['annual'])} (write the number with thousands separators, e.g. USD {money(spec['annual'])})")
    if spec.get("total"):
        f.append(f"Total contract value: USD {money(spec['total'])}" + (" (fixed fee for this Work Order)" if t == "Work Order" else ""))
    if spec.get("pay"):
        f.append(f"Payment terms: undisputed invoices payable within {spec['pay']} days of receipt of a valid invoice")
    cap = spec.get("cap")
    if cap == "unlimited":
        f.append("Liability: each party's liability is UNLIMITED (no cap on either party)")
    elif cap == "msa":
        f.append("Liability: governed by the liability provisions of the parent agreement (do not restate a cap)")
    elif cap is not None:
        f.append(f"Liability cap: each party's aggregate liability is limited to {cap:g} times the fees paid or payable in the twelve (12) months preceding the claim (state the multiple {cap:g} explicitly, e.g. 'one (1) times' / 'two (2) times' / '0.5 times')")
    tfc = spec.get("tfc")
    if tfc == "no":
        f.append("Termination for convenience: NOT permitted for either party; termination only for cause")
    elif tfc:
        f.append(f"Termination for convenience: the Customer may terminate without cause on {tfc} days' written notice")
    if spec.get("law"):
        f.append(f"Governing law: {spec['law']} (state exactly 'laws of {spec['law']}')")
    if spec.get("auto") is True:
        f.append(f"Renewal: renews automatically for successive 12-month periods unless a party gives at least {spec['notice']} days' written notice of non-renewal before the end of the then-current term")
    elif spec.get("auto") is False:
        f.append("Renewal: does NOT renew automatically; any extension needs a written agreement")
    if spec.get("sla"):
        f.append(f"Service level: availability of at least {spec['sla']}% each month" + (f"; security incidents notified within {spec['inc']} hours" if spec.get("inc") else ""))
    elif spec.get("inc"):
        f.append(f"Security incidents must be notified within {spec['inc']} hours")
    if spec.get("ins"):
        f.append(f"Insurance: supplier maintains cover of at least USD {money(spec['ins'])} per claim")
    if spec.get("warr") is not None and t not in ("NDA", "DPA"):
        f.append(f"Warranty period: {spec['warr']} days" if spec["warr"] else "Warranty: no express warranty period (services warranty only)")
    if spec.get("conf"):
        f.append(f"Confidentiality obligations survive for {spec['conf']} years after the agreement ends")
    if t not in ("NDA",):
        if spec.get("pd") is True:
            f.append("Personal data: the services involve processing personal data of the Customer's customers and employees" + (" and a Data Processing Agreement is in place (state that a DPA has been or will be executed alongside)" if spec.get("dpa") else " (do NOT mention any Data Processing Agreement; none exists)"))
        elif spec.get("pd") is False:
            f.append("Personal data: the services do NOT involve processing personal data (say so explicitly)")
    for i, (d, _) in enumerate(spec.get("ms") or [], 1):
        f.append(f"Milestone {i}: {d} due {{{{MS{i}}}}} (state the date as the token and keep the milestone number)")
    for e in spec.get("extras") or []:
        f.append(f"Also include this duty: {e}")
    cn, sn = signers(spec)
    sg = spec.get("sign", "both")
    if spec.get("status") == "draft":
        f.append("Signature: blocks are blank and unsigned (draft)")
    elif sg == "both":
        f.append(f"Signed for the Customer by {cn}, {SIGNERS['customer'][0][1] if cn == SIGNERS['customer'][0][0] else SIGNERS['customer'][1][1]}, on {{{{SIGNED_CUSTOMER}}}}; signed for the Supplier by {sn}, Authorised Signatory, on {{{{SIGNED_SUPPLIER}}}}")
    elif sg == "supplier":
        f.append(f"Signed for the Supplier by {sn}, Authorised Signatory, on {{{{SIGNED_SUPPLIER}}}}; the Customer's signature block is still blank (not yet countersigned)")
    return f


def prompt(spec: dict) -> tuple[str, str]:
    system = ("You are a senior commercial contracts lawyer drafting a realistic, complete, internally consistent contract for a " + PACK["domain"] + ". "
              "All parties and people are fictional. Output ONLY the contract as Markdown (a single # title line, then ## headings for clauses, tables as Markdown tables where natural), "
              "with no commentary, no code fences and no notes to the user. Use real contract language, not summaries.")
    style = STYLES[spec["style"]]
    user = f"""Write the full text of this agreement, about 1,200 to 2,200 words.

DRAFTING STYLE: {style}

THE FACTS TO REFLECT EXACTLY (they are ground truth; do not contradict them; do not add other numbers for these terms):
""" + "\n".join(f"- {x}" for x in facts(spec)) + """

RULES
- Where a fact contains a token such as {{EFFECTIVE}}, {{EXPIRY}}, {{SIGNED_CUSTOMER}}, {{SIGNED_SUPPLIER}}, {{PARENT_DATE}}, {{NEW_EXPIRY}}, {{MS1}}, write the token itself exactly (it is replaced by a real date later). Do not invent other dates.
- Cover the usual clauses for this document type in your style (term, fees and invoicing, services/scope, confidentiality, IP, warranties, liability, indemnity, termination, data protection, governing law, assignment, notices, entire agreement), keeping to the facts above. Where the facts are silent on a topic, write a reasonable, balanced clause without stating new numeric limits.
- Make it read like a real contract in the given style, with the structure and heading conventions of that style (not a generic template).
- The document title is a normal contract title (e.g. "Master Services Agreement", "Statement of Work No. 1", "Subscription Agreement"); parties are named in the first paragraph.
"""
    return system, user


def validate(spec: dict, md: str) -> list[str]:
    """Programmatic check that the generated text actually states the spec's facts."""
    t, low, bad = spec["type"], md.lower(), []
    for tok in re.findall(r"\{\{(\w+)\}\}", " ".join(facts(spec))):
        if "{{" + tok + "}}" not in md:
            bad.append(f"missing token {tok}")
    for k in ("annual", "total"):
        if spec.get(k) and money(spec[k]) not in md and f"{spec[k] / 1e6:g} million" not in low:
            bad.append(f"missing {k} {money(spec[k])}")
    if spec.get("law") and spec["law"].lower() not in low:
        bad.append("missing governing law")
    if spec.get("pay") and not re.search(rf"\b{spec['pay']}\b|{_words(spec['pay'])}", low):
        bad.append("missing payment days")
    if spec.get("cap") == "unlimited" and "unlimited" not in low and "no limit" not in low and "not be limited" not in low:
        bad.append("missing unlimited liability")
    if spec.get("sla") and str(spec["sla"]).rstrip("0").rstrip(".") not in md:
        bad.append("missing SLA")
    if len(md.split()) < 500 and t not in ("NDA", "Amendment", "Work Order", "DPA"):
        bad.append("too short")
    if t == "Amendment" and not re.search(r"amend", low):
        bad.append("not an amendment")
    return bad


_W = {15: "fifteen", 20: "twenty", 30: "thirty", 45: "forty-five", 60: "sixty", 90: "ninety"}


def _words(n: int) -> str:
    return _W.get(n, str(n))


# ------------------------------------------------------------------ labels (ground truth from the spec)
def labels(seed: date) -> dict:
    out = {"seed_date": seed.isoformat(), "contracts": {}, "drafts": {}}
    for sp in DOCS:
        d = dates(sp, seed)
        cn, sn = signers(sp)
        sg = sp.get("sign", "both")
        eff, t = d["EFFECTIVE"], sp["type"]
        lab = dict(effective_date=eff.isoformat(), expiry_date=d["EXPIRY"].isoformat())
        if t == "Amendment":
            lab = dict(effective_date=eff.isoformat(), payment_terms_days=sp["ov"]["payment_terms_days"], expiry_date=d["NEW_EXPIRY"].isoformat())
        else:
            tfc = sp.get("tfc")
            cap = sp.get("cap")
            lab.update(
                notice_period_days=sp.get("notice") if sp.get("auto") else None, auto_renew=bool(sp.get("auto")), annual_value=sp.get("annual") or None, total_value=sp.get("total") or None,
                payment_terms_days=sp.get("pay"), liability_cap_multiple=cap if isinstance(cap, (int, float)) else None,
                liability_cap_text=("Unlimited" if cap == "unlimited" else "Governed by MSA" if cap == "msa" else f"{cap:g} times annual fees" if cap is not None else None),
                termination_for_convenience=(False if tfc == "no" else True if tfc else None), governing_law=sp.get("law"),
                processes_personal_data=bool(sp.get("pd")) if t not in ("NDA",) else False, has_dpa=bool(sp.get("dpa")) if t not in ("DPA", "NDA") else False)
        draft = sp.get("status") == "draft"
        lab.update(customer_signatory=cn if (not draft and sg in ("both", "customer")) else None, customer_signed_date=d["SIGNED_CUSTOMER"].isoformat() if (not draft and sg in ("both", "customer")) else None,
                   supplier_signatory=sn if (not draft and sg in ("both", "supplier")) else None, supplier_signed_date=d["SIGNED_SUPPLIER"].isoformat() if (not draft and sg in ("both", "supplier")) else None,
                   fully_executed=bool(not draft and sg == "both"))
        lab["values"] = {k: v for k, v in dict(payment_terms_days=sp.get("pay"), sla_availability_pct=sp.get("sla"), incident_notice_hours=sp.get("inc"), insurance_cover_usd=sp.get("ins"), warranty_days=sp.get("warr") or None,
                                               confidentiality_years=sp.get("conf"), renewal_notice_days=sp.get("notice") if sp.get("auto") else None, tfc_notice_days=int(sp["tfc"]) if str(sp.get("tfc") or "").isdigit() else None).items() if v is not None}
        lab["milestones"] = [{"title": m, "date": d[f"MS{i}"].isoformat()} for i, (m, _) in enumerate(sp.get("ms") or [], 1)]
        lab["deviations"] = sp.get("dev", [])
        lab["meta"] = dict(property=sp.get("prop"), key=sp["key"], type=t, vendor=sp["vendor"], status="draft" if draft else "active", parent=sp.get("parent") or sp.get("amends"), category=sp["cat"], owner=sp["owner"])
        (out["drafts"] if draft else out["contracts"])[sp["key"]] = lab
    return out


# ------------------------------------------------------------------ rendering into the inbox
def fill(md: str, spec: dict, seed: date) -> str:
    fmt = "%B %d, %Y" if PACK["name"] == "hotel" else DATE_FMT[spec["style"]]          # the hotel group is a United States business: month-first dates throughout
    for k, v in dates(spec, seed).items():
        s = v.strftime(fmt)
        md = md.replace("{{" + k + "}}", s.replace(" 0", " ") if fmt.startswith("%d") else re.sub(r" 0(\d),", r" \1,", s))
    eff = dates(spec, seed)["EFFECTIVE"]

    def mobilisation(m):          # a milestone token the text uses but the spec gives no date for: a mobilisation date two weeks per step after the start, never a raw token
        s = (eff + timedelta(days=14 * int(m.group(1)))).strftime(fmt)
        return s.replace(" 0", " ") if fmt.startswith("%d") else re.sub(r" 0(\d),", r" \1,", s)

    return re.sub(r"\{\{MS(\d)\}\}", mobilisation, md)


def _convert(md_path: Path, out: Path, fmt: str) -> bool:
    if not shutil.which("pandoc"):
        return False
    docx = out if fmt == "docx" else out.with_suffix(".docx")
    r = subprocess.run(["pandoc", str(md_path), "-f", "markdown", "-o", str(docx)], capture_output=True, text=True)
    if r.returncode != 0:
        return False
    if fmt == "pdf":
        if not shutil.which("soffice"):
            docx.unlink(missing_ok=True)
            return False
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", td, str(docx)], capture_output=True, text=True, timeout=180)
            pdf = Path(td) / (docx.stem + ".pdf")
            if not pdf.exists():
                docx.unlink(missing_ok=True)
                return False
            shutil.move(str(pdf), str(out))
        docx.unlink(missing_ok=True)
    return True


def render(root: Path, seed: date, formats: bool = True) -> dict:
    """Write the pilot corpus into root/inbox/{contracts,drafts}/ in each document's own format (md / docx / pdf) plus labels.json."""
    cdir, ddir = root / "inbox" / "contracts", root / "inbox" / "drafts"
    for d in (cdir, ddir):
        d.mkdir(parents=True, exist_ok=True)
        for f in list(d.glob("*")):          # files, and folders a connector pulled into (a re-seed starts from the corpus alone)
            shutil.rmtree(f) if f.is_dir() else f.unlink()
    n, fallbacks = 0, []
    for sp in DOCS:
        src = CORPUS_DIR / f"{sp['key']}.md"
        if not src.exists():
            raise FileNotFoundError(f"{src} is missing: run scripts/build_pilot_corpus.py")
        md = fill(src.read_text(), sp, seed)
        dest = (ddir if sp.get("status") == "draft" else cdir)
        want = sp["fmt"] if formats else "md"
        target = dest / f"{sp['key']}.{want}"
        tmp = Path(tempfile.mkdtemp()) / f"{sp['key']}.md"
        tmp.write_text(md)
        if want == "md" or not _convert(tmp, target, want):
            if want != "md":
                fallbacks.append(sp["key"])
            target = dest / f"{sp['key']}.md"
            target.write_text(md)
        target.with_suffix(".meta.json").write_text(json.dumps({k: v for k, v in {"category": sp["cat"], "owner": sp["owner"], "property": sp.get("prop")}.items() if v}))
        n += 1
    lab = labels(seed)
    (root / PACK["labels"]).write_text(json.dumps(lab, indent=1))
    (root / PACK["manifest"]).write_text(json.dumps({"seed_date": seed.isoformat(), "customer": CUSTOMER, "corpus": PACK["name"], "documents": n, "format_fallbacks": fallbacks}, indent=1))
    return {"documents": n, "format_fallbacks": fallbacks}
