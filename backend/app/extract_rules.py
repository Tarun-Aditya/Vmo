"""Rule-based field extraction that does not depend on a template's exact wording: normalised text (number words, '(30)' duplicates,
USD), several phrasings per field, clause-scoped search with a whole-document fallback, many date formats. Same output shape as the Claude
extractor: {field: {value, confidence, clause_type, page}}."""
from __future__ import annotations

import re
from datetime import date, timedelta

from app import textutil as tu
from app.config import settings


def customer_markers() -> list[str]:
    return [m.strip().lower() for m in (settings.customer_names or "arcadia").split(",") if m.strip()]


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _add_months(d: date, n: int) -> date:
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    for day in (d.day, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


class Doc:
    def __init__(self, md: str, header: dict, clauses: list[dict], doc_type: str):
        self.md, self.header, self.clauses, self.type = md, header, clauses, doc_type
        self.body = tu.normalize(re.sub(r"<!--.*?-->", " ", md))
        self.flat = re.sub(r"\s+", " ", self.body)
        self.by = {}
        for c in clauses:
            self.by.setdefault(c["clause_type"], []).append(c)

    def scoped(self, *types: str) -> str:
        return " ".join(tu.normalize(c["text"]) for t in types for c in self.by.get(t, []))

    def search(self, pattern: str, types: tuple[str, ...] = (), flags=re.I) -> tuple[re.Match | None, str | None]:
        """First match in the clauses of those types, else anywhere. Returns (match, clause_type_or_None)."""
        for t in types:
            for c in self.by.get(t, []):
                m = re.search(pattern, tu.normalize(c["text"]), flags)
                if m:
                    return m, t
        m = re.search(pattern, self.flat, flags)
        return m, None

    def page_of(self, ctype: str | None) -> int:
        c = self.by.get(ctype, [None])[0] if ctype else None
        return c["page"] if c else 1


def _first_para(d: Doc) -> str:
    return d.flat[:2200]


def extract(md: str, header: dict, clauses: list[dict], doc_type: str) -> dict:
    d = Doc(md, header, clauses, doc_type)
    out: dict[str, dict] = {}
    amend = doc_type == "Amendment"

    def put(field, value, conf, ctype=None):
        out[field] = dict(value=value, confidence=conf if value is not None else min(conf, 0.5), clause_type=ctype if ctype in d.by else None, page=d.page_of(ctype))

    # ---- effective date
    head = _first_para(d)
    eff = None
    for rx in (r"(?:effective (?:as of|on|date)|entered into (?:as of|on)|made (?:as of|on|and entered into on)|is dated|dated as of|as of|commenc\w+ on|starts? on)[:\s|*]*([^.;]{0,40})",
               r"Effective Date[\s|:*]+([^\n|]{4,40})", r"Period[\s|:*]+([^\n|]{4,40}?)(?:\s+(?:to|through|until|–|-)\s+)"):
        for m in re.finditer(rx, head, re.I):
            eff = tu.first_date(m.group(1))
            if eff:
                break
        if eff:
            break
    if not eff:
        eff = tu.first_date(head)
    put("effective_date", _iso(eff), 0.95 if eff else 0.3)

    # ---- expiry
    expiry, ec = None, "term"
    m, ec = d.search(r"(?:now expires? on|extended to|until|expires? on|expiring on|ends? on|end date[:\s|]*|continues? (?:in (?:full )?(?:force|effect) )?until|through|terminat\w+ on)[:\s|*]*([A-Za-z0-9,/ .\-]{6,30})", ("term",))
    if m:
        expiry = tu.first_date(m.group(1))
    if not expiry:
        m, ec = d.search(r"(?:initial term|term of|period of|for a term of|for an initial period of|for)\s+(?:this agreement\s+)?(?:is\s+)?(\d+(?:\.\d+)?)\s+(months?|years?)", ("term",))
        if m and eff:
            n = float(m.group(1)) * (12 if m.group(2).lower().startswith("y") else 1)
            expiry = _add_months(eff, int(round(n)))
    put("expiry_date", _iso(expiry), 0.93 if expiry else 0.3, ec)

    # ---- renewal
    if not amend or re.search(r"renew", d.flat, re.I):
        rtxt = d.scoped("renewal", "term") or d.flat
        auto = None
        if re.search(r"(does not|will not|shall not|not)\s+(?:renew|be renewed|automatically renew|auto-?renew)|no automatic renewal|not subject to automatic renewal|any extension (?:of the term )?requires|may be extended only by", rtxt, re.I):
            auto = False
        elif re.search(r"renews? automatically|automatically renews?|auto-?renew|automatic(?:ally)? renew|successive (?:renewal )?(?:terms|periods)|renewal terms?", rtxt, re.I):
            auto = True
        if auto is None and not amend:
            put("auto_renew", False, 0.6)
            put("notice_period_days", None, 0.6)
        elif auto is not None:
            put("auto_renew", auto, 0.93, "renewal" if "renewal" in d.by else "term")
            n = None
            if auto:
                mm = re.search(r"(?:at least|not less than|no later than|not (?:fewer|less) than|prior to the end[^.]{0,40}?by giving)\s*(\d+)\s*days", rtxt, re.I) or re.search(r"(\d+)\s*days[’']?\s*(?:prior |advance )?(?:written )?notice[^.]{0,60}(?:non-?renewal|not to renew|renew)", rtxt, re.I) or re.search(r"(?:non-?renewal|not to renew)[^.]{0,80}?(\d+)\s*days", rtxt, re.I)
                n = int(mm.group(1)) if mm else None
            put("notice_period_days", n, 0.9 if n else 0.4, "renewal" if "renewal" in d.by else "term")
    # ---- fees
    if not amend:
        amounts = []
        A_CUE = r"annual|per year|each year|yearly|per annum|12-month|first year|year one|subscription fee|per contract year|a year"
        T_CUE = r"total|aggregate|fixed fee|not[- ]to[- ]exceed|contract value|total fees|total charges|for the (?:initial )?term|overall|in total|capped at|value of this"
        for m in re.finditer(r"USD\s*([\d,]{4,}(?:\.\d+)?)(?:\s*(million))?", d.flat):
            v = float(m.group(1).replace(",", "")) * (1e6 if m.group(2) else 1)
            before, after = d.flat[max(0, m.start() - 90):m.start()].lower(), d.flat[m.end():m.end() + 28].lower()
            if re.search(r"insur|per claim|\bcap\b|liabilit|exceed the greater|aggregate liability|indemn|penalt|credit", before[-70:] + after) and not re.search(r"fees?", before[-50:]):
                continue
            amounts.append((v, before, after))
        annual = total = None
        for v, before, after in amounts:
            ca = max((x.end() for x in re.finditer(A_CUE, before)), default=-1)
            ct = max((x.end() for x in re.finditer(T_CUE, before)), default=-1)
            if re.search(r"per year|annually|a year|per annum|each year|/yr", after):
                ca = max(ca, len(before))
            if ca > ct and annual is None:
                annual = v
            elif ct > ca and total is None:
                total = v
        if annual is None and total is None and amounts:
            annual = total = amounts[0][0] if doc_type in ("SaaS", "SOW", "Work Order") else None
        elif annual is not None and total is None and eff and expiry and doc_type in ("SaaS", "SOW"):
            months = round((expiry - eff).days / 30.44)
            total = round(annual * months / 12, 2) if months not in (0, 12) else annual
        elif total is not None and annual is None and eff and expiry and (expiry - eff).days <= 380:
            annual = total if doc_type != "Work Order" else None
        put("annual_value", annual, 0.88 if annual else 0.5, "fees" if "fees" in d.by else None)
        put("total_value", total, 0.88 if total else 0.5, "fees" if "fees" in d.by else None)
    # ---- payment terms
    pm, pc = d.search(r"(?:pay|payable|payment|invoice|remit)[^.]{0,160}?within\s+(\d+)\s+(?:calendar\s+)?days|\bnet\s*(\d+)\b|within\s+(\d+)\s+(?:calendar\s+)?days\s+(?:of|after|from)[^.]{0,40}(?:receipt|invoice|date of invoice)|(\d+)\s+days\s+(?:from|after|of)\s+(?:receipt of|the date of)\s+(?:a\s+|the\s+|each\s+)?(?:valid\s+)?invoice", ("payment", "fees"))
    n = next((int(g) for g in pm.groups() if g), None) if pm else None
    if amend:
        am = re.search(r"payment terms?[^.]{0,120}?(\d+)\s*days|(?:within|net)\s*(\d+)\s*days", d.flat, re.I)
        n = next((int(g) for g in am.groups() if g), None) if am else None
        if n:
            put("payment_terms_days", n, 0.9, "payment")
    elif d.type not in ("NDA",):
        put("payment_terms_days", n, 0.9 if n else 0.4, pc)
    # ---- liability
    if True:
        ltxt = d.scoped("liability_cap")
        if not ltxt:
            m = re.search(r"(limitation of liability|liability cap|cap on liability)[^.]*\.([^§]{0,900})", d.flat, re.I)
            ltxt = (m.group(0) if m else "")
        lc = "liability_cap" if "liability_cap" in d.by else None
        if ltxt:
            low = ltxt.lower()
            if re.search(r"unlimited|no (?:limit|cap)|not be (?:subject to any )?(?:limit|cap)|uncapped|without (?:any )?limit", low) and not re.search(r"nothing in this agreement (?:shall|will) (?:limit|exclude)", low[:0]):
                put("liability_cap_multiple", None, 0.9, lc)
                put("liability_cap_text", "Unlimited", 0.9, lc)
            else:
                mm = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|times)\b|(\d+)\s*%\s*of", ltxt, re.I)
                half = re.search(r"\bone[- ]half\b|\bhalf of\b", ltxt, re.I)
                if mm and mm.group(1):
                    v = float(mm.group(1))
                    put("liability_cap_multiple", v, 0.92, lc)
                    put("liability_cap_text", f"{v:g} times annual fees", 0.92, lc)
                elif mm and mm.group(2):
                    v = int(mm.group(2)) / 100
                    put("liability_cap_multiple", v, 0.85, lc)
                    put("liability_cap_text", f"{v:g} times annual fees", 0.85, lc)
                elif half:
                    put("liability_cap_multiple", 0.5, 0.8, lc)
                    put("liability_cap_text", "0.5 times annual fees", 0.8, lc)
                elif re.search(r"(?:fees|charges|amounts?)\s+(?:paid|payable|paid or payable)[^.]{0,80}(?:12|twelve)\s+months|(?:12|twelve)\s+months[^.]{0,80}(?:fees|charges)", ltxt, re.I):
                    put("liability_cap_multiple", 1.0, 0.85, lc)
                    put("liability_cap_text", "1 times annual fees", 0.85, lc)
                elif re.search(r"(?:master|parent|governed by|provisions of the|as set out in the|set out in the)[^.]{0,60}(?:agreement|msa|sow)", ltxt, re.I):
                    put("liability_cap_multiple", None, 0.88, lc)
                    put("liability_cap_text", "Governed by MSA", 0.88, lc)
                else:
                    put("liability_cap_multiple", None, 0.3, lc)
        else:
            put("liability_cap_multiple", None, 0.6)
            put("liability_cap_text", None, 0.6)
    # ---- termination for convenience
    if not amend:
        ttxt = d.scoped("termination_for_convenience") or " ".join(re.findall(r"[^.]*\bconvenience\b[^.]*\.", d.flat))
        tc = "termination_for_convenience" if "termination_for_convenience" in d.by else None
        if re.search(r"neither party (?:may|shall|will|can) terminate[^.]{0,80}convenience|(?:no|not)[^.]{0,40}(?:right|entitled|permitted)[^.]{0,40}terminate[^.]{0,60}(?:convenience|without cause)|only (?:for|upon) (?:cause|material breach)|not (?:be )?(?:entitled|permitted)[^.]{0,40}convenience|(?:cannot|may not|shall not) be terminated for convenience|no (?:termination|right to terminate) for convenience", ttxt, re.I):
            put("termination_for_convenience", False, 0.92, tc)
        elif re.search(r"(?:may|can|shall be entitled to)\s+terminate[^.]{0,120}(?:for convenience|without cause|for any reason)|for convenience[^.]{0,60}(?:upon|on|by giving|with)[^.]{0,30}\d+\s*days", ttxt, re.I):
            put("termination_for_convenience", True, 0.9, tc)
        else:
            put("termination_for_convenience", None, 0.4, tc)
    # ---- governing law
    if not amend:
        m, gc = d.search(r"(?:governed by|construed in accordance with|subject to)[^.]{0,50}?laws? of (?:the )?(?:State of |Commonwealth of |Republic of )?((?:England and Wales|Northern Ireland|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}))(?:,|\.| without| and | excluding| including| applicable| for| \(|;)", ("governing_law",), flags=0)
        v = m.group(1).strip() if m else None
        put("governing_law", v, 0.93 if v else 0.4, gc)
    # ---- personal data and DPA
    if not amend:
        scope = d.flat
        neg = re.search(r"(?:do(?:es)? not|will not|shall not|no)\s+(?:involve|include|require|entail|process)[^.]{0,40}personal data|no personal data", scope, re.I)
        pos = re.search(r"(?:services?|engagement|work|supplier|vendor|[A-Z][a-z]+)\s+(?:will|shall|may|does|do)?\s*(?:involve|include|require|entail)s?[^.]{0,50}(?:process\w*|access\w*|handl\w*)[^.]{0,30}personal (?:data|information)|(?:will|may|does|do|shall)\s+(?:have access to|process|handle|receive|store|access)\s+(?:the\s+)?(?:customer'?s?\s+)?personal (?:data|information)(?!\s+only)|personal (?:data|information) of (?:the )?(?:customer|arcadia|its)[^.]{0,40}(?:will|is|are|may|shall) (?:be )?(?:process|access|stor|handl)", scope, re.I)
        pd = False if neg else bool(pos) and d.type != "NDA"
        put("processes_personal_data", pd, 0.8, "data_protection" if "data_protection" in d.by else None)
        dpa = bool(re.search(r"(?:executed|entered into|signed|agreed|concluded|put in place)\s+(?:a|an|the)\s+(?:data processing (?:agreement|addendum)|dpa)|(?:data processing (?:agreement|addendum)|\bDPA\b)[^.]{0,60}(?:dated|forms? part|is attached|has been (?:executed|entered|signed)|is in place|is incorporated|governs|supplements|(?:has|have) been)|(?:data processing (?:agreement|addendum)|\bDPA\b)[^.]{0,30}(?:executed|signed) (?:alongside|concurrently|together)", scope, re.I)) and not re.search(r"no (?:dpa|data processing agreement)|(?:must|shall|will|to) be (?:executed|entered into|signed)[^.]{0,30}before|not (?:yet )?(?:entered into|executed|in place)[^.]{0,30}(?:dpa|data processing)", scope, re.I)
        put("has_dpa", dpa and d.type not in ("DPA", "NDA"), 0.75)
    # ---- signatures
    cs, ss = signatures(d)
    ctype = "execution" if "execution" in d.by else None
    for pre, s in (("customer", cs), ("supplier", ss)):
        put(f"{pre}_signatory", s[0] if s else None, 0.9 if s else 0.5, ctype)
        put(f"{pre}_signed_date", _iso(s[1]) if s else None, 0.9 if s and s[1] else 0.5, ctype)
    put("fully_executed", bool(cs and ss), 0.88, ctype)
    return out


NAME = r"[A-Z][A-Za-z.'\-]+(?:\s+[A-Z][A-Za-z.'\-]+){1,3}"


def signatures(d: Doc) -> tuple[tuple | None, tuple | None]:
    """(customer, supplier) -> (name, date | None) or None. Handles 'Signed ... by X, Title, on DATE' sentences, By/Name/Title/Date blocks and tables."""
    cm = customer_markers()
    tail = d.md[-6000:]
    res: dict[str, tuple] = {}
    # sentence form
    for m in re.finditer(rf"(?i:signed|executed|countersigned)\b[^\n]{{0,60}}?(?i:for and on behalf of|on behalf of|for)\s+(?:the\s+)?(?P<party>[^\n]{{2,90}}?)\s+by\s+(?P<name>{NAME})\s*,\s*(?P<title>[^,\n]{{2,70}}?),?\s*(?i:on|dated)\s+(?P<date>[A-Za-z0-9,/ \-]{{6,24}})", tail):
        role = "customer" if any(k in m.group("party").lower() for k in cm + ["customer", "client"]) else "supplier"
        res.setdefault(role, (m.group("name").strip(), tu.first_date(m.group("date"))))
    # blocks: lines with Name:
    lines = [re.sub(r"[|*_`]", " ", ln).strip() for ln in tail.splitlines()]
    for i, ln in enumerate(lines):
        mm = re.match(rf"^(?:Printed )?Name\s*[:\-]?\s*(?P<name>{NAME})\s*$", ln)
        if not mm:
            continue
        window = lines[max(0, i - 9):i + 6]
        date_ = None
        for w in lines[i:i + 6]:
            dm = re.match(r"^Date(?: signed)?\s*[:\-]?\s*(.+)$", w)
            if dm:
                date_ = tu.first_date(dm.group(1))
                break
        ctx = " ".join(lines[max(0, i - 9):i]).lower()
        role = "customer" if any(k in ctx[-300:] for k in cm + ["customer", "client"]) and not any(k in ctx[-120:] for k in ("supplier", "vendor")) else "supplier"
        if ctx.rfind(cm[0]) > ctx.rfind("supplier"):
            role = "customer"
        res.setdefault(role, (mm.group("name").strip(), date_))
        _ = window
    # form: 'Signed: Name  Date: ...' inside a table row
    for m in re.finditer(rf"(?P<party>Customer|Client|Supplier|Vendor|Arcadia[^|\n]*)\s*\|\s*(?P<name>{NAME})\s*\|[^|\n]*\|\s*(?P<date>[A-Za-z0-9,/ .\-]{{6,30}})", tail):
        role = "customer" if any(k in m.group("party").lower() for k in cm + ["customer", "client"]) else "supplier"
        res.setdefault(role, (m.group("name").strip(), tu.first_date(m.group("date"))))
    return res.get("customer"), res.get("supplier")
