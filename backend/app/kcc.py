"""Configurable libraries that drive identification, extraction and review:

* KCC library   - key contract clauses: what to identify (keywords / heading aliases), what the
                  standard says, whether it shows in the matrix.
* Metrics       - values and limits to extract from a clause (regex -> number/text), e.g. payment
                  terms days, liability cap multiple, insurance cover USD.
* Checklist     - rules run on a contract before signing: clause required / forbidden, metric
                  threshold (<=, >=, =), forbidden wording. Severity + suggested wording.

Defaults ("builtin") are seeded from the clause library; admins can edit them and add their own.
The pipeline and the UI read these tables, so a change applies everywhere."""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.docgen.library import CLAUSES, KEY_CLAUSES, TEMPLATES, clause_text, standard_text

TYPE_OF_TEMPLATE = {"MSA": "MSA", "SOW": "SOW", "WO": "Work Order", "NDA": "NDA", "SaaS": "SaaS", "DPA": "DPA"}
DOC_TYPES = ["MSA", "SOW", "Work Order", "NDA", "SaaS", "DPA", "Amendment"]

# Extra identification hints for the builtin clauses: heading aliases and body keywords.
ALIASES: dict[str, list[str]] = {
    "term": ["Duration", "Term of Agreement"],
    "renewal": ["Auto-Renewal", "Renewal Term"],
    "payment": ["Fees and Payment", "Invoicing", "Payment Terms", "Invoicing and Payment"],
    "termination_for_cause": ["Termination for Breach"],
    "liability_cap": ["Liability", "Liability Cap", "Cap on Liability"],
    "indemnity": ["Indemnification"],
    "ip_ownership": ["IP Ownership", "Ownership of Work Product"],
    "confidentiality": ["Non-Disclosure"],
    "data_protection": ["Data Privacy", "Privacy"],
    "audit_rights": ["Audit"],
    "non_solicit": ["Non-Solicit"],
    "governing_law": ["Governing Law and Jurisdiction", "Jurisdiction"],
    "sla": ["SLA", "Service Level Agreement"],
    "security": ["Security"],
    "data_return": ["Data Return", "Exit and Data Return"],
    "acceptance": ["Acceptance Testing"],
    "change_control": ["Change Management"],
    "subprocessors": ["Subprocessors"],
    "breach_notification": ["Data Breach Notification"],
    "warranties": ["Warranty"],
    "dispute_resolution": ["Disputes"],
    "order_of_precedence": ["Precedence", "Conflicts"],
    "governance": ["Governance"],
}
KEYWORDS: dict[str, list[str]] = {
    "term": ["commences on", "expires on", "initial term"],
    "renewal": ["renews automatically", "non-renewal", "auto-renew"],
    "payment": ["undisputed invoices", "payment terms", "valid invoice"],
    "termination_for_convenience": ["for convenience", "without cause", "for any reason", "without reason"],
    "termination_for_cause": ["material breach", "not remedied within"],
    "liability_cap": ["aggregate liability", "limitation of liability", "liability is unlimited", "liability under this"],
    "indemnity": ["shall indemnify", "indemnification", "third-party claims"],
    "ip_ownership": ["owns all", "work product", "intellectual property"],
    "confidentiality": ["confidential information"],
    "data_protection": ["data protection law", "documented instructions", "personal data"],
    "audit_rights": ["audit the supplier", "right to audit", "audit rights"],
    "assignment": ["assign this"],
    "non_solicit": ["solicit for employment"],
    "governing_law": ["governed by the laws", "exclusive jurisdiction"],
    "sla": ["availability each month", "service credits", "service levels"],
    "security": ["security incident", "iso 27001"],
    "data_return": ["return or securely delete", "certify the deletion"],
    "acceptance": ["acceptance in writing", "deemed accepted"],
    "change_control": ["change request"],
    "subprocessors": ["sub-processor"],
    "breach_notification": ["personal data breach"],
    "cross_border": ["transfer personal data", "outside the united states"],
    "return_info": ["return or destroy"],
    "services": ["services described in each statement of work"],
    "order_of_precedence": ["prevail", "in case of conflict", "if there is a conflict"],
    "warranties": ["warrants that", "warranty"],
    "insurance": ["insurance", "per claim"],
    "force_majeure": ["beyond its reasonable control", "force majeure"],
    "dispute_resolution": ["escalated", "mediation", "arbitration"],
    "key_personnel": ["key personnel"],
    "governance": ["service review meeting", "monthly report"],
    "execution": ["signed for and on behalf", "signature pending"],
    "fees": ["annual fees", "fixed fee"],
    "msa_reference": ["issued under the master services agreement"],
    "sow_reference": ["issued under sow", "issued under the statement of work"],
    "deliverables": ["milestone 1"],
    "data_scope": ["processing of personal data"],
    "dpa_reference": ["data processing agreement dated"],
}


def default_kcc() -> list[dict]:
    out = []
    for i, (key, c) in enumerate(CLAUSES.items()):
        expected = sorted({TYPE_OF_TEMPLATE[t] for t, d in TEMPLATES.items() if key in d["clauses"]})
        doc = next((TEMPLATES[t]["doc"] for t in TEMPLATES if key in TEMPLATES[t]["clauses"]), "Agreement")
        out.append(dict(
            key=key, name=c.heading, description=(c.playbook or c.heading), category="Key clause" if key in KEY_CLAUSES else "Document element",
            keywords=KEYWORDS.get(key, []), heading_aliases=[c.heading] + ALIASES.get(key, []),
            standard_text=None if c.variable else standard_text(key, doc),
            playbook_position=c.playbook or None,
            fallback_text=(c.fallback.format(doc=doc, **{"warranty_days": 60}) if c.fallback else None) or None,
            severity_if_missing=c.severity_if_missing, applies_to=expected,
            in_matrix=key in KEY_CLAUSES, enabled=True, sort_order=i, builtin=True,
        ))
    return out


def _m(key, name, kcc, pattern, kind, unit, desc):
    return dict(key=key, name=name, kcc_key=kcc, pattern=pattern, kind=kind, unit=unit, description=desc,
                scale=1, enabled=True, builtin=True)


def default_metrics() -> list[dict]:
    return [
        _m("payment_terms_days", "Payment terms", "payment", r"(?:within|net)\s+(\d+)(?:\s+calendar)?(?:\s+days)?", "number", "days", "Days to pay undisputed invoices"),
        _m("liability_cap_multiple", "Liability cap multiple", "liability_cap", r"([\d.]+)\s*(?:times|x)\b", "number", "x annual fees", "Cap on liability as a multiple of annual fees"),
        _m("tfc_notice_days", "Termination for convenience notice", "termination_for_convenience", r"(\d+) days['’]? (?:prior )?(?:written )?notice", "number", "days", "Notice the Customer must give to terminate for convenience"),
        _m("renewal_notice_days", "Non-renewal notice period", "renewal", r"(?:at least|not less than|no later than)\s+(?:[a-z\- ]+\()?(\d+)(?:\s*\(\d+\))?\)?\s+days", "number", "days", "Notice needed to stop an auto-renewal"),
        _m("insurance_cover_usd", "Insurance cover per claim", "insurance", r"USD\s*([\d,]{5,})", "money", "USD", "Minimum professional indemnity cover per claim"),
        _m("warranty_days", "Warranty period", "warranties", r"(\d+)\s*days?\s+(?:after|from|following)\s+(?:the\s+(?:date|day)\s+)?(?:of\s+)?(?:acceptance|delivery|completion|go-live|performance|[^.]{0,50}(?:delivered|accepted|performed))|warranty period of (\d+) days|(?:for a period of|period of)\s+(\d+)\s*days[^.]{0,40}(?:performance|delivery|acceptance)|warrant\w*[^.]{0,120}?(?:period of|for)\s+(\d+)\s*days|(\d+)\s*days[^.]{0,80}warranty period", "number", "days", "Free-of-charge correction period after acceptance"),
        _m("confidentiality_years", "Confidentiality survival", "confidentiality", r"(?:for|period of|survive[sd]? for|continue[sd]? for)\s+(?:a period of\s+)?(\d+)\s+years?", "number", "years", "Years confidentiality survives the agreement"),
        _m("sla_availability_pct", "Service availability", "sla", r"([\d.]+)\s*%\s*(?:availability|uptime|monthly|of (?:each|every|the) (?:calendar )?(?:month|time))|(?:availability|uptime|available)[^.]{0,80}?([\d.]+)\s*%", "number", "%", "Monthly availability commitment"),
        _m("incident_notice_hours", "Security incident notice", "security", r"within (\d+) (hours|days)", "number", "hours", "Time to notify a security incident"),
        _m("breach_notice_hours", "Personal data breach notice", "breach_notification", r"within (\d+) (hours|days)", "number", "hours", "Time to notify a personal data breach"),
        _m("cure_period_days", "Cure period for breach", "termination_for_cause", r"within (\d+) days", "number", "days", "Days to remedy a material breach"),
        _m("key_personnel_replacement_days", "Key personnel replacement", "key_personnel", r"within (\d+) days", "number", "days", "Days to provide an equivalent replacement"),
        _m("acceptance_days", "Acceptance testing window", "acceptance", r"not less than (\d+) business days", "number", "business days", "Customer testing period"),
        _m("audit_notice_days", "Audit notice", "audit_rights", r"(\d+) days' notice", "number", "days", "Notice needed before an audit"),
        _m("force_majeure_termination_days", "Force majeure termination trigger", "force_majeure", r"(?:more than|exceed[s]?|longer than|in excess of)\s+(\d+)\s+days", "number", "days", "Days of force majeure before termination"),
        _m("governing_law_text", "Governing law", "governing_law", r"laws? of (?:the )?(?:State of |Commonwealth of )?(England and Wales|Northern Ireland|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2})(?:,|\.| without| and | excluding| \(|;)", "text", "", "Jurisdiction whose law governs"),
    ]


def _r(key, name, desc, rtype, sev, applies, *, kcc=None, metric=None, op=None, num=None, txt=None, phrase=None,
       stage="any", fix=None):
    return dict(key=key, name=name, description=desc, rule_type=rtype, kcc_key=kcc, metric_key=metric, operator=op,
                threshold=num, threshold_text=txt, phrase=phrase, severity=sev, applies_to=applies, stage=stage,
                suggested_text=fix, enabled=True, builtin=True)


def _fix(ctype: str, doc: str = "Agreement") -> str:
    return standard_text(ctype, doc)


def default_rules() -> list[dict]:
    M, S, W, N, SA, D, A = "MSA", "SOW", "Work Order", "NDA", "SaaS", "DPA", "Amendment"
    return [
        _r("liability_cap_required", "Liability cap clause present", "Every MSA and SaaS agreement must cap liability.", "clause_required", "high", [M, SA], kcc="liability_cap", fix=_fix("liability_cap")),
        _r("liability_cap_max", "Liability cap ≤ 2× annual fees", "Cap on liability must not exceed 2× annual fees (standard 1×).", "metric_threshold", "high", [M, SA], metric="liability_cap_multiple", op="<=", num=2, fix=_fix("liability_cap")),
        _r("no_unlimited_liability", "No unlimited liability", "Unlimited liability exposes the Customer and is never acceptable.", "text_forbidden", "critical", [M, SA, S], phrase=r"unlimited", fix=_fix("liability_cap")),
        _r("payment_terms_min", "Payment terms ≥ 30 days", "Never accept terms shorter than 30 days.", "metric_threshold", "high", [M, S, W, SA], metric="payment_terms_days", op=">=", num=30, fix=_fix("payment")),
        _r("payment_terms_target", "Payment terms ≥ 45 days (target)", "Standard is Net 45.", "metric_threshold", "low", [M, S, W, SA], metric="payment_terms_days", op=">=", num=45, fix=_fix("payment")),
        _r("tfc_required", "Termination for convenience present", "Customer must be able to exit without cause.", "clause_required", "high", [M, S, SA], kcc="termination_for_convenience", fix=_fix("termination_for_convenience")),
        _r("tfc_not_barred", "Termination for convenience not barred", "Clause must not bar termination for convenience.", "text_forbidden", "high", [M, S, SA], kcc="termination_for_convenience", phrase=r"neither party may terminate", fix=_fix("termination_for_convenience")),
        _r("tfc_notice_max", "Termination notice ≤ 90 days", "Convenience termination notice should not exceed 90 days.", "metric_threshold", "medium", [M, S, SA], metric="tfc_notice_days", op="<=", num=90, fix=_fix("termination_for_convenience")),
        _r("renewal_notice_min", "Auto-renewal notice ≥ 60 days", "Auto-renewals need a workable notice window.", "metric_threshold", "medium", [M, SA], metric="renewal_notice_days", op=">=", num=60, fix=_fix("renewal")),
        _r("insurance_required", "Insurance clause present", "Supplier must carry professional indemnity insurance.", "clause_required", "medium", [M], kcc="insurance", fix=_fix("insurance")),
        _r("insurance_min", "Insurance cover ≥ USD 2,000,000", "Minimum cover per claim (standard USD 5,000,000).", "metric_threshold", "medium", [M], metric="insurance_cover_usd", op=">=", num=2_000_000, fix=_fix("insurance")),
        _r("warranty_min", "Warranty period ≥ 60 days", "Warranty must run at least 60 days (standard 90).", "metric_threshold", "medium", [M], metric="warranty_days", op=">=", num=60, fix=_fix("warranties")),
        _r("no_warranty_disclaimer", "No blanket warranty disclaimer", "", "text_forbidden", "high", [M], kcc="warranties", phrase=r"disclaims all warranties", fix=_fix("warranties")),
        _r("confidentiality_min_years", "Confidentiality survives ≥ 3 years", "Confidentiality must survive at least 3 years (standard 3).", "metric_threshold", "high", [M, N, SA], metric="confidentiality_years", op=">=", num=3, fix=_fix("confidentiality")),
        _r("sla_min", "Availability SLA ≥ 99.5%", "Hosted services must commit to at least 99.5% availability.", "metric_threshold", "high", [SA], metric="sla_availability_pct", op=">=", num=99.5, fix=_fix("sla")),
        _r("sla_credits", "Service credits apply", "No 'no service credits' wording.", "text_forbidden", "high", [SA, S], phrase=r"no service credits", fix=_fix("sla")),
        _r("incident_notice_max", "Security incident notice ≤ 72 hours", "Incident notice within 72 hours (standard 48).", "metric_threshold", "high", [SA, M], metric="incident_notice_hours", op="<=", num=72, fix=_fix("security")),
        _r("breach_notice_max", "Personal data breach notice ≤ 72 hours", "Breach notice within 72 hours (standard 48).", "metric_threshold", "critical", [D, SA], metric="breach_notice_hours", op="<=", num=72, fix=_fix("breach_notification")),
        _r("data_protection_required", "Data protection clause present", "Required wherever personal data may be processed.", "clause_required", "critical", [M, SA, D], kcc="data_protection", fix=_fix("data_protection")),
        _r("no_discretionary_processing", "No discretionary data processing", "", "text_forbidden", "critical", [M, SA, D], kcc="data_protection", phrase=r"considers appropriate", fix=_fix("data_protection")),
        _r("audit_required", "Audit rights present", "Customer needs audit rights.", "clause_required", "medium", [M, D], kcc="audit_rights", fix=_fix("audit_rights")),
        _r("no_audit_waiver", "Audit rights not waived", "", "text_forbidden", "high", [M, D], kcc="audit_rights", phrase=r"no right to audit", fix=_fix("audit_rights")),
        _r("indemnity_required", "Supplier indemnity present", "Supplier must indemnify for IP infringement, breach of law and gross negligence.", "clause_required", "high", [M], kcc="indemnity", fix=_fix("indemnity")),
        _r("indemnity_direction", "Indemnity runs from the Supplier", "", "text_forbidden", "high", [M], kcc="indemnity", phrase=r"the customer shall indemnify", fix=_fix("indemnity")),
        _r("ip_customer_owned", "Customer owns bespoke deliverables", "", "text_forbidden", "high", [M, SA, S], phrase=r"the supplier owns all deliverables", fix=_fix("ip_ownership")),
        _r("precedence_required", "Order of precedence present", "SOWs and Work Orders must sit under the MSA.", "clause_required", "high", [M, S, W], kcc="order_of_precedence", fix=_fix("order_of_precedence", "SOW")),
        _r("msa_prevails", "MSA prevails over SOW/Work Order", "", "text_forbidden", "high", [S, W], phrase=r"prevails over the master services agreement", fix=_fix("order_of_precedence", "SOW")),
        _r("governing_law_ny", "Governed by New York law", "Standard governing law; others need Legal approval.", "metric_threshold", "medium", [M, N, SA, D], metric="governing_law_text", op="=", txt="New York", fix=_fix("governing_law")),
        _r("no_free_personnel_swap", "Key personnel cannot be swapped freely", "", "text_forbidden", "medium", [S], kcc="key_personnel", phrase=r"replace any personnel at any time", fix=_fix("key_personnel", "SOW")),
        _r("no_deemed_acceptance", "No deemed acceptance", "", "text_forbidden", "medium", [S, W], kcc="acceptance", phrase=r"deemed accepted", fix=_fix("acceptance", "SOW")),
        _r("subprocessor_consent", "Sub-processors need consent", "", "text_forbidden", "high", [D], kcc="subprocessors", phrase=r"at its discretion", fix=_fix("subprocessors")),
        _r("no_open_transfers", "No unrestricted cross-border transfers", "", "text_forbidden", "critical", [D], kcc="cross_border", phrase=r"any country", fix=_fix("cross_border")),
        _r("force_majeure_narrow", "Force majeure is not a blanket excuse", "", "text_forbidden", "medium", [M], kcc="force_majeure", phrase=r"labour shortages", fix=_fix("force_majeure")),
        _r("executed", "Signed by both parties", "Executed documents must carry both signatures.", "clause_required", "high", [M, S, W, N, SA, D, A], kcc="execution", stage="post_sign"),
    ]


# ------------------------------------------------------------------ persistence
KCC_COLS = ["key", "name", "description", "category", "keywords", "heading_aliases", "standard_text", "playbook_position",
            "fallback_text", "severity_if_missing", "applies_to", "in_matrix", "enabled", "sort_order", "builtin"]
MET_COLS = ["key", "name", "description", "kcc_key", "pattern", "kind", "unit", "scale", "enabled", "builtin"]
RULE_COLS = ["key", "name", "description", "rule_type", "kcc_key", "metric_key", "operator", "threshold", "threshold_text", "phrase",
             "severity", "applies_to", "stage", "suggested_text", "enabled", "builtin"]


def _insert_missing(s, table: str, cols: list[str], rows: list[dict]) -> int:
    have = {r[0] for r in s.execute(text(f"SELECT key FROM {table}"))}
    n = 0
    for r in rows:
        if r["key"] in have:
            continue
        s.execute(text(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"), {c: r.get(c) for c in cols})
        n += 1
    return n


def refresh_builtins(s) -> int:
    """Bring the built-in metric patterns up to date with the code (seed / upgrade). Rules and metrics added by admins are never touched."""
    n = 0
    for m in default_metrics():
        r = s.execute(text("UPDATE metrics SET pattern=:p, kind=:k, unit=:u, kcc_key=:kk WHERE key=:key AND builtin AND (pattern IS DISTINCT FROM :p OR kcc_key IS DISTINCT FROM :kk)"),
                      {"p": m["pattern"], "k": m["kind"], "u": m["unit"], "kk": m["kcc_key"], "key": m["key"]})
        n += r.rowcount
    return n


def ensure_defaults(s) -> dict:
    """Insert any missing builtin config rows (never overwrites admin edits) and rebuild the matrix view."""
    out = {
        "kcc": _insert_missing(s, "kcc_library", KCC_COLS, default_kcc()),
        "metrics": _insert_missing(s, "metrics", MET_COLS, default_metrics()),
    }
    rules = default_rules()
    for i, r in enumerate(rules):
        r["sort_order"] = i
    out["rules"] = _insert_missing(s, "checklist_rules", RULE_COLS + ["sort_order"], rules)
    s.execute(text("INSERT INTO pipeline_config (id, key, name, folders) VALUES (1, 'contracts', 'Executed contracts', 'contracts,uploads') ON CONFLICT DO NOTHING"))
    s.execute(text("INSERT INTO pipeline_config (id, key, name, folders, trigger_mode, interval_minutes) VALUES (2, 'drafts', 'Draft review (redline)', 'drafts,generated', 'on_change', 15) ON CONFLICT DO NOTHING"))
    s.execute(text("INSERT INTO pipeline_config (id, key, name, folders, trigger_mode, interval_minutes) VALUES (3, 'feeds', 'Operational feeds', 'feeds', 'on_change', 60) ON CONFLICT DO NOTHING"))
    from app import config_items

    config_items.ensure_defaults(s)
    rebuild_key_clauses_view(s)
    return out


def _rows(s, sql: str) -> list[dict[str, Any]]:
    return [dict(r) for r in s.execute(text(sql)).mappings().all()]


def load_kcc(s, only_enabled: bool = True) -> list[dict]:
    return _rows(s, "SELECT * FROM kcc_library " + ("WHERE enabled " if only_enabled else "") + "ORDER BY sort_order, key")


def load_metrics(s, only_enabled: bool = True) -> list[dict]:
    return _rows(s, "SELECT * FROM metrics " + ("WHERE enabled " if only_enabled else "") + "ORDER BY key")


def load_rules(s, only_enabled: bool = True) -> list[dict]:
    return _rows(s, "SELECT * FROM checklist_rules " + ("WHERE enabled " if only_enabled else "") + "ORDER BY sort_order, key")


def matrix_keys(s) -> list[str]:
    return [r["key"] for r in _rows(s, "SELECT key FROM kcc_library WHERE enabled AND in_matrix ORDER BY sort_order, key")]


def rebuild_key_clauses_view(s) -> None:
    """has_<key> columns follow the KCC library, so adding a clause adds a column everywhere (matrix, Ask)."""
    from app.viewsql import key_clauses_sql

    keys = matrix_keys(s) or list(KEY_CLAUSES)
    s.execute(text("DROP VIEW IF EXISTS v_key_clauses"))
    s.execute(text(key_clauses_sql(keys)))
    s.execute(text("GRANT SELECT ON v_key_clauses TO vmo_readonly"))


# ------------------------------------------------------------------ classification
def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def classify(heading: str, body: str, kcc: list[dict]) -> str:
    """Map a clause to a KCC key: exact heading alias, then alias contained in the heading,
    then the best keyword score over the body. 'other' if nothing matches."""
    h = _norm(re.sub(r"^(?:article|section|clause)\s+[ivxlc\d]+\s*[-–—.:]*\s*|^\d+(?:\.\d+)*[\.\)]?\s*|^[-–—]+\s*", "", heading.replace("--", "–"), flags=re.I))
    for k in kcc:
        if h in {_norm(a) for a in (k["heading_aliases"] or [])} or h == _norm(k["name"]):
            return k["key"]
    best, score = "other", 0
    inside: tuple[int, str] | None = None          # 'Data Protection and Payment-Card Security' is a data-protection heading, not a payment one: the longest alias wins
    for k in kcc:
        n = max((len(_norm(a)) for a in (k["heading_aliases"] or []) if len(a) > 4 and re.search(rf"\b{re.escape(_norm(a))}\b", h)), default=0)
        if n and (inside is None or n > inside[0]) and _confirmed(k["key"], body):
            inside = (n, k["key"])
    if inside:
        return inside[1]
    b = _norm(body)
    for k in kcc:
        sc = sum(1 for kw in (k["keywords"] or []) if kw and re.search(kw, b, re.I) if _safe_re(kw))
        if sc > score and _confirmed(k["key"], body):
            best, score = k["key"], sc
    return best


def _confirmed(key: str, body: str) -> bool:
    """A clause matched only loosely (alias inside a heading, or body keywords) is accepted for a key that has a precise sentence pattern only if the pattern really matches:
    real contracts have table-of-contents lines, boilerplate and licences that merely mention 'termination' or 'insurance'. An exact heading match is always accepted."""
    return True if key not in PRESENCE else bool(sentence_hits(key, body or ""))


def _safe_re(p: str) -> bool:
    try:
        re.compile(p)
        return True
    except re.error:
        return False


# ------------------------------------------------------------------ metric extraction
def extract_metrics(clauses: list[dict], metrics: list[dict], kcc_cfg: list[dict] | None = None) -> list[dict]:
    """clauses: {id?, clause_type, text, page}. Returns [{metric_key, value_num, value_text, clause_id, page, confidence}].
    A metric is read from the clauses of its KCC type; when the document has no such clause (real contracts merge or rename them) the pattern is tried
    on the sentences of the whole document that carry one of that KCC clause's keywords."""
    from app import textutil as tu

    by_type: dict[str, list[dict]] = {}
    for c in clauses:
        by_type.setdefault(c["clause_type"], []).append(c)
    kw = {k["key"]: [w for w in (k.get("keywords") or []) if w and _safe_re(w)] for k in (kcc_cfg or [])}
    names = {k["key"]: k["name"] for k in (kcc_cfg or [])}
    for m in metrics:       # the words of the metric's own and its clause's name (stems) also mark a sentence as relevant: 'availability' ~ 'available'
        stems = {w[:6] for w in re.findall(r"[a-z]{5,}", f"{m.get('name', '')} {names.get(m.get('kcc_key'), '')}".lower())}
        if m["kcc_key"] and stems:
            kw.setdefault(m["kcc_key"], [])
            kw[m["kcc_key"]] = list(dict.fromkeys(kw[m["kcc_key"]] + [rf"\b{x}\w*" for x in stems]))
    out = []
    for m in metrics:
        if not _safe_re(m["pattern"]):
            continue
        typed = by_type.get(m["kcc_key"]) if m["kcc_key"] else clauses
        attempts = [(typed, False)] if typed else []
        if m["kcc_key"] and kw.get(m["kcc_key"]):      # the clause may be missing or merged / mis-typed: also try the keyword sentences of the whole document
            attempts.append((clauses, True))
        found = False
        for pool, sentence_mode in attempts:
            for c in pool:
                text_ = tu.normalize(c["text"])
                if sentence_mode:
                    sents = [x for x in re.split(r"(?<=[.;])\s+", text_) if any(re.search(w, x, re.I) for w in kw[m["kcc_key"]])]
                    text_ = " ".join(sents)
                mt = re.search(m["pattern"], text_, re.I)
                if not mt:
                    continue
                g = next((x for x in mt.groups() if x and re.search(r"\d|\w", x)), None)
                if g is None:
                    continue
                row = dict(metric_key=m["key"], value_num=None, value_text=None, clause_id=c.get("id"), page=c.get("page"), confidence=0.85 if sentence_mode else 0.92)
                if m["kind"] == "text":
                    row["value_text"] = g.strip()
                else:
                    try:
                        v = float(g.replace(",", "")) * float(m.get("scale") or 1)
                    except ValueError:
                        continue
                    unit_g = mt.group(2) if mt.lastindex and mt.lastindex >= 2 else None
                    if unit_g and unit_g.lower().startswith("day") and (m.get("unit") or "") == "hours":
                        v *= 24
                    row["value_num"] = v
                out.append(row)
                found = True
                break
            if found:
                break
    return out


# ------------------------------------------------------------------ checklist engine
OPS = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b, ">": lambda a, b: a > b, "=": lambda a, b: a == b}


def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:g}"


def evaluate_rules(doc_type: str, status: str, clauses: list[dict], values: list[dict], metrics: list[dict],
                   rules: list[dict], fully_executed: bool, category: str | None = None) -> list[dict]:
    """Run the enabled checklist rules. Returns a result per applicable rule:
    {rule_key, status: pass|fail|na, actual, expected, severity, clause_id, page, excerpt}."""
    by_type: dict[str, list[dict]] = {}
    for c in clauses:
        by_type.setdefault(c["clause_type"], []).append(c)
    vals = {v["metric_key"]: v for v in values}
    unit = {m["key"]: (m.get("unit") or "") for m in metrics}
    out = []
    for r in rules:
        if r["applies_to"] and doc_type not in r["applies_to"]:
            continue
        if r.get("categories") and category not in r["categories"]:        # a rule for one kind of supplier says nothing about the others
            continue
        if r["stage"] == "post_sign" and status == "draft":
            continue
        res = dict(rule_key=r["key"], status="na", actual=None, expected=None, severity=r["severity"], clause_id=None, page=None, excerpt=None)
        t = r["rule_type"]
        if t == "clause_required":
            cl = by_type.get(r["kcc_key"], [])
            present = fully_executed if r["kcc_key"] == "execution" else bool(cl)
            res.update(status="pass" if present else "fail", expected="required", actual="present" if present else "missing")
            if cl:
                res.update(clause_id=cl[0].get("id"), page=cl[0].get("page"), excerpt=cl[0]["text"][:300])
        elif t == "clause_forbidden":
            cl = by_type.get(r["kcc_key"], [])
            res.update(status="fail" if cl else "pass", expected="absent", actual="present" if cl else "absent")
            if cl:
                res.update(clause_id=cl[0].get("id"), page=cl[0].get("page"), excerpt=cl[0]["text"][:300])
        elif t == "text_forbidden":
            pool = by_type.get(r["kcc_key"], []) if r["kcc_key"] else clauses
            if r["kcc_key"] and not pool:
                res.update(status="na")
            else:
                hit = next((c for c in pool if _safe_re(r["phrase"] or "") and re.search(r["phrase"], c["text"], re.I)), None)
                res.update(status="fail" if hit else "pass", expected=f"no “{(r['phrase'] or '').replace(chr(92), '')}”", actual="found" if hit else "not found")
                if hit:
                    res.update(clause_id=hit.get("id"), page=hit.get("page"), excerpt=hit["text"][:300])
        elif t == "metric_threshold":
            v = vals.get(r["metric_key"])
            u = unit.get(r["metric_key"], "")
            if r["operator"] == "=" and r["threshold_text"] is not None:
                res["expected"] = f"= {r['threshold_text']}"
                if v and v["value_text"] is not None:
                    ok = _norm(v["value_text"]) == _norm(r["threshold_text"])
                    res.update(status="pass" if ok else "fail", actual=v["value_text"], clause_id=v["clause_id"], page=v["page"])
            else:
                thr = float(r["threshold"]) if r["threshold"] is not None else 0.0
                res["expected"] = f"{ {'<=': '≤', '>=': '≥'}.get(r['operator'], r['operator']) } {_fmt(thr)} {u}".strip()
                if v and v["value_num"] is not None:
                    ok = OPS[r["operator"]](float(v["value_num"]), thr)
                    res.update(status="pass" if ok else "fail", actual=f"{_fmt(float(v['value_num']))} {u}".strip(), clause_id=v["clause_id"], page=v["page"])
            if v and v.get("clause_id"):
                c = next((c for c in clauses if c.get("id") == v["clause_id"]), None)
                res["excerpt"] = c["text"][:300] if c else None
        out.append(res)
    return out


__all__ = ["ensure_defaults", "load_kcc", "load_metrics", "load_rules", "classify", "extract_metrics", "evaluate_rules", "DOC_TYPES", "clause_text"]


# ------------------------------------------------------------------ sentence-level clause detection (real contracts bury clauses inside other sections, or have no usable headings)
PRESENCE = {
    "audit_rights": r"\b(?:examin\w+|review\w*)\b[^.;]{0,80}\b(?:books|records)\b|\b(?:books|records)\b[^.;]{0,100}\b(?:available (?:for|to)|examin\w+)|available for audit|\b(?:audit|inspect)\w*\b[^.;]{0,100}\b(?:books|records|facilit\w+|premises|accounts)|\b(?:books|records|accounts)\b[^.;]{0,100}\b(?:audit|inspect)\w*|right to (?:audit|inspect)|access (?:to|during)[^.;]{0,80}\b(?:records|books|facilit\w+)",
    "assignment": r"\b(?:neither|no|none of the)\s+(?:party|parties)\b[^.;]{0,60}\b(?:may|shall|will|can)\b[^.;]{0,40}\b(?:assign|transfer|cede|delegate)\w*|\b(?:may|shall|will|can)\s+not\s+(?:\w+\s+){0,4}?(?:assign|transfer)\w*\b|\bno\s+(?:party|assignment)[^.;]{0,60}\b(?:assign|transfer)|assign\w*[^.;]{0,100}without[^.;]{0,50}(?:prior )?(?:written )?consent|(?:prior )?(?:written )?consent[^.;]{0,60}to (?:any )?assign",
    "termination_for_convenience": r"\btermination for convenience\b|\bterminat\w*[^.;]{0,40}\bfor (?:its |their )?convenience\b|\bfor convenience\b[^.;]{0,40}\bterminat\w*|\b(?:may|can|shall have the right to|has the right to|have the right to|is entitled to|reserves the right to|may elect to)\s+(?:\w+\s+){0,3}?terminate\b[^.;]{0,200}?(?:without cause|for any reason|for no reason|at any time|(?:upon|on|with|by giving|after)[^.;]{0,40}\d+\)?\s*(?:calendar |business )?(?:days|months)|prior written notice)|\b(?:may|can|shall) be terminated[^.;]{0,200}?(?:without cause|for any reason|for no reason|at any time|(?:upon|on|with|by giving)[^.;]{0,40}\d+\)?\s*(?:calendar |business )?(?:days|months)|prior written notice)|\bcancell?able at any time",
    "liability_cap": r"\bliability\b[^.;]{0,100}(?:governed by|set out in|subject to|as provided in|as stated in|per)[^.;]{0,60}(?:agreement|msa)|limitation[s]? (?:of|on) liability|\b(?:total|maximum|aggregate|entire) liability\b|(?:shall|will) not be liable[^.;]{0,120}(?:indirect|consequential|special|incidental|punitive|exemplary|lost profits)|(?:neither|no) party[^.;]{0,80}liab\w+[^.;]{0,160}(?:indirect|consequential|special|incidental|punitive|exemplary|lost profits)|(?:in no event|under no circumstances|shall not)[^.;]{0,250}(?:liab\w+|damages)[^.;]{0,250}(?:exceed|in excess of|limited to|not be greater than)|(?:liab\w+|damages)[^.;]{0,120}(?:shall|will) not exceed|aggregate liability|liability (?:is|shall be) (?:limited|capped)",
    "insurance": r"\b(?:maintain|carry|procure|keep)\b[^.;]{0,100}\binsurance\b|\binsurance (?:coverage|polic\w+|certificate)|certificates? of insurance|general liability insurance",
    "ip_ownership": r"\b(?:ownership|owns?|owned by|title to|belongs? to)\b[^.;]{0,100}\b(?:developed|created|conceived|invented|work product|deliverables|improvements|inventions|intellectual property|results)\b|\b(?:developed|created|conceived|invented|generated)\b[^.;]{0,120}\b(?:shall|will) (?:be|remain|belong)\b[^.;]{0,50}(?:property|owned|owner|belong)|hereby assigns?[^.;]{0,80}(?:right, title|intellectual property|work product|inventions)|assigns?[^.;]{0,60}right, title and interest|work made for hire|(?:shall|will) (?:be|remain) the (?:sole |exclusive )?property of",
    "non_solicit": r"non-?solicit\w*|(?:shall|will|agrees?|covenants?) not[^.;]{0,80}\bsolicit\w*|\bsolicit\w*[^.;]{0,60}\b(?:employees|customers|personnel|clients)",
}


# sentences that look like a match but are not (a termination for breach / insolvency, or a survival clause), skipped for that key
NEGATIVE = {"ip_ownership": r"\b(?:grants?|licen[sc]e[ds]?|sublicen[sc]\w*)\b(?![^.;]*(?:work made for hire|hereby assign))", "termination_for_convenience": r"\b(?:breach|default|insolven\w*|bankrupt\w*|failure to|fails? to|surviv\w+|for cause|material)\b(?![^.;]*(?:without cause|for convenience))|\bnotwithstanding any termination\b"}


def sentence_hits(key: str, text_: str) -> list[str]:
    cre, neg = re.compile(PRESENCE[key], re.I), re.compile(NEGATIVE[key], re.I) if key in NEGATIVE else None
    return [s for s in re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", text_)) if cre.search(s) and not (neg and neg.search(s))]


def detect_in_text(clauses: list[dict], md: str, have_types: set[str], enabled: set[str] | None = None, extra: dict[str, list[str]] | None = None) -> list[dict]:
    """Extra clause records for key clauses that no heading-based clause carries, found by sentence in the clause texts (or, when the document yielded no clauses, in its paragraphs).
    Each record keeps the matching sentence(s) as its text and the page of the clause it came from, so the matrix, checklist and Ask can cite it."""
    pools = [(c["text"], c.get("page", 1), c.get("heading") or "Text") for c in clauses] or [(p, 1, "Text") for p in re.split(r"\n\s*\n", md)]
    out: list[dict] = []
    patterns = {**{k: None for k in PRESENCE}, **{k: re.compile("|".join(f"(?:{kw})" for kw in kws if _safe_re(kw)), re.I) for k, kws in (extra or {}).items() if any(_safe_re(kw) for kw in kws)}}
    for key, custom in patterns.items():
        if key in have_types or (enabled is not None and key not in enabled):
            continue
        best: tuple[int, dict] | None = None
        for text_, page, head in pools:
            hit = sentence_hits(key, text_) if custom is None else [s for s in re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", text_)) if custom.search(s)]
            if hit:
                rec = {"clause_type": key, "heading": f"{head[:60]} (found in text)", "text": " ".join(hit[:2])[:900], "page": page, "idx": 0}
                if custom is None:
                    best = (1, rec)
                    break
                # an admin's clause: the passage matching most of its keywords, not the first mention (a definition that names 'payment-card data' is not the PCI clause)
                score = sum(1 for kw in (extra or {}).get(key, []) if _safe_re(kw) and re.search(kw, rec["text"], re.I))
                if best is None or score > best[0]:
                    best = (score, rec)
        if best:
            out.append(best[1])
    return out
