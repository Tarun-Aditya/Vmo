"""Generate the 28 fictional documents, the manifest (catalogue metadata) and labels.json
(ground truth) from the library + specs. Dates are relative to the seed date."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from app.docgen.library import (
    CLAUSES,
    CUSTOMER,
    STD,
    TEMPLATES,
    VARIANTS,
    clause_text,
    standard_text,
)
from app.docgen.specs import CONTRACTS, CUSTOMER_SIGNERS, DRAFTS, VENDOR_SIGNERS

KEY_FIELDS = [
    "effective_date",
    "expiry_date",
    "notice_period_days",
    "auto_renew",
    "annual_value",
    "total_value",
    "payment_terms_days",
    "liability_cap_multiple",
    "termination_for_convenience",
    "governing_law",
    "processes_personal_data",
    "has_dpa",
    "customer_signatory",
    "customer_signed_date",
    "supplier_signatory",
    "supplier_signed_date",
    "fully_executed",
]


def inr(n: int) -> str:
    """US digit grouping: 4800000 -> 4,800,000 (name kept for the callers)."""
    return f"{int(n):,}"


def long_date(d: date) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def _layout(title: str, header: list[str], clauses: list[tuple[str, str]]) -> str:
    """Markdown with page markers: header + first 2 clauses on page 1, then 3 clauses per page."""
    out = ["<!-- page: 1 -->", f"# {title}", ""] + header + [""]
    page = 1
    for i, (heading, text) in enumerate(clauses):
        if i >= 2 and (i - 2) % 3 == 0:
            page += 1
            out += [f"<!-- page: {page} -->", ""]
        out += [f"## {i + 1}. {heading}", text, ""]
    return "\n".join(out)


def inheritance_ctx(spec: dict, seed: date, by_key: dict[str, dict]) -> dict:
    """Text that ties a SOW to its MSA and a Work Order to its SOW (and MSA): built on top of the
    parent documents, so the references always name real parents and dates."""
    parent = by_key.get(spec.get("parent", ""), {})
    out: dict = {}
    if spec["type"] == "SOW" and parent:
        out["msa_reference_text"] = (
            f"This SOW is issued under the Master Services Agreement dated "
            f"{long_date(seed + timedelta(days=parent['eff']))} between the parties "
            f"({parent['title']}). Capitalised terms have the meaning given in that agreement."
        )
    if spec["type"] == "Work Order" and parent:
        msa = by_key.get(parent.get("parent", ""), {})
        out["sow_reference_text"] = (
            f"This Work Order is issued under {parent['title']} (effective "
            f"{long_date(seed + timedelta(days=parent['eff']))})"
            + (
                f" and the Master Services Agreement dated "
                f"{long_date(seed + timedelta(days=msa['eff']))}."
                if msa
                else "."
            )
        )
    eff, exp = seed + timedelta(days=spec["eff"]), seed + timedelta(days=spec["exp"])
    span = (exp - eff).days
    d1, d2 = eff + timedelta(days=14), eff + timedelta(days=min(90, span // 2))
    d3 = eff + timedelta(days=min(180, max(span - 14, 30)))
    out["deliverables_text"] = (
        f"Milestone 1: mobilisation and delivery plan by {long_date(d1)}. Milestone 2: core "
        f"delivery by {long_date(d2)}. Milestone 3: handover and written acceptance by "
        f"{long_date(d3)}."
    )
    return out


def execution_block(spec: dict, eff: date) -> tuple[str, dict]:
    """Signature clause text + the signature labels. The Supplier may be unsigned (planted)."""
    cust = CUSTOMER_SIGNERS["legal" if spec["type"] in ("NDA", "DPA") else "default"]
    sup = VENDOR_SIGNERS[spec["vendor"]]
    cd, sd = eff - timedelta(days=3), eff - timedelta(days=2)
    text = (
        f"Signed for and on behalf of {CUSTOMER} (the Customer) by {cust[0]}, {cust[1]}, "
        f"on {long_date(cd)}. "
    )
    labels = dict(
        customer_signatory=cust[0],
        customer_signed_date=cd.isoformat(),
        supplier_signatory=None,
        supplier_signed_date=None,
        fully_executed=False,
    )
    if spec.get("unsigned_supplier"):
        text += (
            f"Supplier signature pending: {spec['vendor']} (the Supplier) has not yet "
            "countersigned this document."
        )
    else:
        text += (
            f"Signed for and on behalf of {spec['vendor']} (the Supplier) by {sup[0]}, {sup[1]}, "
            f"on {long_date(sd)}."
        )
        labels.update(
            supplier_signatory=sup[0], supplier_signed_date=sd.isoformat(), fully_executed=True
        )
    return text, labels


def _header(vendor: str | None, eff: str, dtype: str, ref: str, draft: bool = False) -> list[str]:
    sup = vendor or "[Supplier]"
    lines = [
        f'**Parties:** {CUSTOMER} (the "Customer") and {sup} (the "Supplier")',
        f"**Effective Date:** {eff}",
        f"**Document Type:** {dtype}",
        f"**Reference:** {ref}",
    ]
    if draft:
        lines.append("**Status:** DRAFT proposed by the Supplier – not executed")
    return lines


def render_template(ttype: str) -> tuple[str, list[dict]]:
    t = TEMPLATES[ttype]
    doc = t["doc"]
    clauses = [(CLAUSES[c].heading, standard_text(c, doc)) for c in t["clauses"]]
    md = _layout(
        f"Standard Template – {t['name']} (v1.0)",
        _header(None, "[Effective Date]", ttype, f"ARC-TPL-{ttype}"),
        clauses,
    )
    meta = [
        dict(
            clause_type=c,
            standard_text=standard_text(c, doc),
            playbook_position=CLAUSES[c].playbook,
            fallback_text=CLAUSES[c].fallback.format(**{**STD, "doc": doc}) or None,
            severity_if_missing=CLAUSES[c].severity_if_missing,
        )
        for c in t["clauses"]
    ]
    return md, meta


def _apply_variants(base: dict, devs: list[str]) -> tuple[dict, dict]:
    """Return (fields-after-variants, {ctype: variant_name})."""
    fields, chosen = dict(base), {}
    for d in devs:
        ct, vn = d.split(":")
        chosen[ct] = vn
        fields.update(VARIANTS[ct][vn].fields)
    return fields, chosen


def build_contract(spec: dict, seed: date, by_key: dict[str, dict]) -> tuple[str, dict, dict]:
    ttype = spec["template"]
    tdef = TEMPLATES[ttype]
    doc = tdef["doc"] if spec["type"] != "Amendment" else "Agreement"
    clauses_in = tdef["clauses"]
    eff, exp = seed + timedelta(days=spec["eff"]), seed + timedelta(days=spec["exp"])
    parent = by_key.get(spec.get("parent", ""), {})

    if spec["type"] == "Amendment":
        return _build_amendment(spec, seed, eff, exp, parent)

    base = dict(
        effective_date=eff.isoformat(),
        expiry_date=exp.isoformat(),
        notice_period_days=None,
        auto_renew=False,
        annual_value=spec.get("annual"),
        total_value=spec.get("total"),
        payment_terms_days=STD["payment_terms_days"] if "payment" in clauses_in else None,
        liability_cap_multiple=(1.0 if "liability_cap" in clauses_in and ttype != "SOW" else None),
        termination_for_convenience=True if "termination_for_convenience" in clauses_in else None,
        governing_law=STD["governing_law"] if "governing_law" in clauses_in else None,
        processes_personal_data=bool(spec.get("pd")),
        has_dpa=bool(spec.get("dpa")),
    )
    if spec.get("auto"):
        base["notice_period_days"] = spec["notice"]
    devs = list(spec.get("dev", []))
    fields, chosen = _apply_variants(base, devs)
    cap_text = (
        "Governed by MSA"
        if ttype == "SOW"
        else fields.get("liability_cap_text")
        or (f"{STD['cap']} times annual fees" if fields["liability_cap_multiple"] else None)
    )
    if fields["liability_cap_multiple"] == 2.0:
        cap_text = "2 times annual fees"
    if "liability_cap" not in clauses_in:
        cap_text = None
    exec_text, exec_labels = execution_block(spec, eff)
    ctx = dict(
        effective_date=long_date(eff),
        expiry_date=long_date(exp),
        annual_value=inr(spec.get("annual") or 0),
        total_value=inr(spec.get("total") or 0),
        scope_text=spec.get("scope", ""),
        notice_period_days=spec.get("notice"),
        dpa_date=long_date(eff + timedelta(days=14)),
        execution_text=exec_text,
        **inheritance_ctx(spec, seed, by_key),
        data_scope_text=(
            f"The services involve the processing of personal data of the "
            f"Customer's {spec.get('subjects')}."
            if spec.get("pd")
            else "The services do not involve the processing of personal data."
        ),
    )
    if ttype == "DPA":
        ctx["scope_text"] = (
            f"This DPA supplements the {parent.get('title', 'main agreement')} "
            "and applies to all personal data the Supplier processes on behalf "
            "of the Customer."
        )
    seq = []
    for c in clauses_in:
        if c == "dpa_reference" and not spec.get("dpa"):
            continue
        seq.append((CLAUSES[c].heading, clause_text(c, doc, ctx, chosen.get(c))))
    ref = f"ARC-{ttype}-{spec['key'].upper()}"
    md = _layout(spec["title"], _header(spec["vendor"], long_date(eff), spec["type"], ref), seq)
    labels = {k: fields.get(k) for k in KEY_FIELDS if k not in exec_labels}
    labels.update(exec_labels)
    labels["liability_cap_text"] = cap_text
    labels["deviations"] = [
        dict(
            clause_type=d.split(":")[0],
            variant=d.split(":")[1],
            severity=VARIANTS[d.split(":")[0]][d.split(":")[1]].severity,
            summary=VARIANTS[d.split(":")[0]][d.split(":")[1]].summary,
        )
        for d in devs
    ]
    return md, labels, {"ctx": ctx}


def _build_amendment(spec, seed, eff, exp, parent):
    seq, labels = [], {"effective_date": eff.isoformat()}
    ctx = dict(effective_date=long_date(eff), expiry_date=long_date(exp))
    for ctype, o in spec["amend"]:
        c = {**ctx, **o}
        if ctype == "term":
            text = (
                f"The expiry date of the Agreement is extended so that the Agreement expires "
                f"on {long_date(exp)}."
            )
            labels["expiry_date"] = exp.isoformat()
        elif ctype == "payment":
            text = clause_text("payment", "Agreement", c)
            labels["payment_terms_days"] = o["payment_terms_days"]
        elif ctype == "liability_cap":
            text = clause_text("liability_cap", "Agreement", c)
            labels["liability_cap_multiple"] = float(o["cap"])
            labels["liability_cap_text"] = f"{o['cap']} times annual fees"
        seq.append((CLAUSES[ctype].heading, text))
    exec_text, exec_labels = execution_block(spec, eff)
    seq.append((CLAUSES["execution"].heading, exec_text))
    labels.update(exec_labels)
    ref = f"ARC-AMD-{spec['key'].upper()}"
    header = _header(spec["vendor"], long_date(eff), "Amendment", ref) + [
        f"**Amends:** {parent['title']}",
        "This Amendment overrides the clauses listed below; "
        "all other terms of the Agreement continue unchanged.",
    ]
    md = _layout(spec["title"], header, seq)
    labels["deviations"] = []
    return md, labels, {}


def build_draft(spec: dict) -> tuple[str, dict]:
    ttype = spec["template"]
    tdef = TEMPLATES[ttype]
    doc = tdef["doc"]
    chosen = dict(d.split(":") for d in spec["dev"])
    ctx = dict(
        effective_date="[Effective Date]",
        expiry_date="[Expiry Date]",
        annual_value="42,00,000",
        total_value="84,00,000",
        scope_text=f"Services to be described by {spec['vendor']}.",
        data_scope_text="The services involve the processing of personal data.",
        dpa_date="[date]",
        notice_period_days=60,
        execution_text="Signature blocks: [Customer signatory: to be signed] [Supplier "
        "signatory: to be signed]. This draft has not been executed.",
        msa_reference_text="This SOW is issued under the Master Services Agreement between the "
        "parties. Capitalised terms have the meaning given in that agreement.",
        deliverables_text="Deliverables and milestones to be agreed.",
    )
    seq = []
    for c in tdef["clauses"]:
        if c in spec["missing"] or c == "dpa_reference":
            continue
        seq.append((CLAUSES[c].heading, clause_text(c, doc, ctx, chosen.get(c))))
    md = _layout(
        spec["title"],
        _header(spec["vendor"], "[to be agreed]", ttype, f"VND-{spec['key'].upper()}", draft=True),
        seq,
    )
    devs = [
        dict(
            clause_type=ct,
            kind="changed",
            variant=vn,
            severity=VARIANTS[ct][vn].severity,
            summary=VARIANTS[ct][vn].summary,
        )
        for ct, vn in chosen.items()
    ]
    devs += [
        dict(
            clause_type=m,
            kind="missing",
            severity=CLAUSES[m].severity_if_missing,
            summary=f"{CLAUSES[m].heading} clause is missing",
        )
        for m in spec["missing"]
    ]
    return md, {"deviations": devs}


def _clean(d: Path) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for f in list(d.glob("*.md")) + list(d.glob("*.meta.json")):
        f.unlink()


def generate(root: Path, seed: date) -> dict:
    """Write the corpus under root:
    templates/*.md                      standard templates (loaded as templates)
    inbox/contracts/*.md + .meta.json   executed contracts, as if dropped into the watched folder
    inbox/drafts/*.md    + .meta.json   vendor drafts (status=draft)
    manifest.json / labels.json         catalogue + ground truth, used only by the evals."""
    tdir, cdir, ddir = root / "templates", root / "inbox" / "contracts", root / "inbox" / "drafts"
    for d in (tdir, cdir, ddir, root / "inbox" / "generated", root / "inbox" / "uploads"):
        _clean(d)
    manifest = dict(
        seed_date=seed.isoformat(), customer=CUSTOMER, currency="USD", templates=[], contracts=[], drafts=[]
    )
    labels = dict(seed_date=seed.isoformat(), contracts={}, drafts={})
    for tt, t in TEMPLATES.items():
        md, _ = render_template(tt)
        rel = f"templates/template_{tt.lower()}.md"
        (root / rel).write_text(md)
        manifest["templates"].append(
            dict(key=tt.lower(), name=f"{t['name']} (Standard)", type=tt, file=rel)
        )
    by_key = {s["key"]: s for s in CONTRACTS}
    for s in CONTRACTS:
        md, lab, _ = build_contract(s, seed, by_key)
        rel = f"inbox/contracts/{s['key']}.md"
        (root / rel).write_text(md)
        parent = by_key.get(s.get("parent", ""), {})
        (root / f"inbox/contracts/{s['key']}.meta.json").write_text(json.dumps({
            "key": s["key"], "category": s["category"], "owner": s["owner"],
            "parent_title": parent.get("title"), "status": "active", "template": s["template"],
        }))
        manifest["contracts"].append(
            {k: s.get(k) for k in ("key", "title", "vendor", "category", "type", "template", "owner", "parent")}
            | {"file": rel}
        )
        labels["contracts"][s["key"]] = lab
    for s in DRAFTS:
        md, lab = build_draft(s)
        rel = f"inbox/drafts/{s['key']}.md"
        (root / rel).write_text(md)
        (root / f"inbox/drafts/{s['key']}.meta.json").write_text(json.dumps({
            "key": s["key"], "category": "Vendor draft", "owner": "Legal Operations",
            "status": "draft", "template": s["template"],
        }))
        manifest["drafts"].append(
            dict(key=s["key"], title=s["title"], vendor=s["vendor"], template=s["template"], file=rel)
        )
        labels["drafts"][s["key"]] = lab
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2))
    (root / "labels.json").write_text(json.dumps(labels, indent=2))
    return manifest


if __name__ == "__main__":
    import sys

    seed = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today()
    m = generate(Path("data"), seed)
    print({k: len(v) for k, v in m.items() if isinstance(v, list)})
