"""Rule-based field extraction that does not depend on a template's exact wording: normalised text (number words, '(30)' duplicates,
USD), several phrasings per field, clause-scoped search with a whole-document fallback, many date formats. Same output shape as the Claude
extractor: {field: {value, confidence, clause_type, page}}."""
from __future__ import annotations

import re
from datetime import date

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
        self.body = tu.normalize(re.sub(r"\*\*|__|`", "", re.sub(r"<!--.*?-->", " ", md)))
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
    eff = None
    for head in (_first_para(d), re.sub(r"\s+", " ", d.flat[:3500])):         # real contracts start with exhibit numbers, redaction notices, tables of contents
        dm = re.search(r"([A-Za-z0-9,/ .\-]{6,40}?)\s*[\(\[]\s*(?:the\s+|this\s+|hereinafter\s+)?[\"“”']?(?:Effective Date|Commencement Date|Start Date)[\"“”']?\s*[\)\]]", head, re.I)
        if dm:
            eff = tu.first_date(dm.group(1))
        for rx in () if eff else (r"(?:effective (?:as of|on|date)|entered into (?:as of|on|this)|made (?:and entered into )?(?:as of|on|this|effective)|is dated|dated (?:as of|this|effective)|as of|commenc\w+ on|starts? on)(?: this)?[:\s|*]*([^.;]{0,40})",
                   r"Effective Date[\s|:*]+([^\n|]{4,40})", r"Period[\s|:*]+([^\n|]{4,40}?)(?:\s+(?:to|through|until|–|-)\s+)"):
            for m in re.finditer(rx, head, re.I):
                eff = tu.first_date(m.group(1))
                if eff:
                    break
            if eff:
                break
        if eff:
            break
        if head is not None and len(head) < 400:
            eff = tu.first_date(head)
            if eff:
                break
    if not eff and not amend:     # the first sentence of the form 'This ... Agreement ... <date>' (not a redaction notice or a date elsewhere)
        for s_ in re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", d.flat[:4000])):
            if re.search(r"\b(?:this|the)\b[^.]{0,100}\bagreement\b", s_, re.I) and (eff := tu.first_date(s_)):
                break
    if not eff:
        eff = tu.first_date(re.sub(r"\s+", " ", d.flat[:3500]))
    put("effective_date", _iso(eff), 0.95 if eff else 0.3)

    # ---- expiry
    expiry, ec = None, "term"
    m, ec = d.search(r"(?:now expires? on|extended to|until|expires? on|expiring on|ends? on|ending on|end date[:\s|]*|continues? (?:in (?:full )?(?:force|effect) )?until|through|terminat\w+ on)[:\s|*]*([A-Za-z0-9,/ .\-]{6,30})", ("term",))
    if m:
        expiry = tu.first_date(m.group(1))
    if not expiry:
        m, ec = d.search(r"(?:initial term|term of|initial period of|period of|for a term of|for an initial (?:term|period) of)\s+(?:this agreement\s+)?(?:is\s+)?(?:of\s+)?(\d+(?:\.\d+)?)\s+(months?|years?)", ("term",))
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
        explicit_total = False
        for v, before, after in amounts:
            ca = max((x.end() for x in re.finditer(A_CUE, before)), default=-1)
            ct = max((x.end() for x in re.finditer(T_CUE, before)), default=-1)
            if re.search(r"per year|annually|a year|per annum|each year|/yr", after):
                ca = max(ca, len(before))
            elif re.match(r"\s*\(\s*(?:the\s+)?(?:total|fixed|aggregate|not[- ]to[- ]exceed)\b", after):      # 'USD 540,000 (total contract value)'
                ct, explicit_total = len(before) + 1, True
            if ca > ct and annual is None:
                annual = v
            elif ct > ca and total is None:
                total = v
        if annual is None and total is None and amounts:
            annual = total = amounts[0][0] if doc_type in ("SaaS", "SOW", "Work Order") else None
        elif annual is not None and total is None and eff and expiry and doc_type in ("SaaS", "SOW"):
            months = round((expiry - eff).days / 30.44)
            total = round(annual * months / 12, 2) if months not in (0, 12) else annual
        elif total is not None and annual is None and eff and expiry and (expiry - eff).days <= 380 and not explicit_total:
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
            numeric = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|times)\b|(\d+)\s*%\s*of|(?:fees|charges|amounts?)\s+(?:paid|payable|paid or payable)[^.]{0,80}(?:12|twelve)\s+months|\bone[- ]half\b", low)
            if not numeric and re.search(r"\bunlimited\b|\bno (?:limit|cap)\b|\bnot be (?:subject to any )?(?:limit|cap)|\buncapped\b|\bwithout (?:any )?limit", low):
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
        elif not amend:
            put("liability_cap_multiple", None, 0.6)
            put("liability_cap_text", None, 0.6)
    # ---- termination for convenience
    if not amend:
        ttxt = d.scoped("termination_for_convenience") or " ".join(re.findall(r"[^.]*\b(?:convenience|without cause|for any reason|without reason)\b[^.]*\.", d.flat))
        tc = "termination_for_convenience" if "termination_for_convenience" in d.by else None
        if re.search(r"neither party (?:may|shall|will|can) terminate[^.]{0,80}convenience|(?:no|not)[^.]{0,40}(?:right|entitled|permitted)[^.]{0,40}terminate[^.]{0,60}(?:convenience|without cause)|only (?:for|upon) (?:cause|material breach)|not (?:be )?(?:entitled|permitted)[^.]{0,40}convenience|(?:cannot|may not|shall not) be terminated for convenience|no (?:termination|right to terminate) for convenience", ttxt, re.I):
            put("termination_for_convenience", False, 0.92, tc)
        elif re.search(r"(?:may|can|shall be entitled to)\s+terminate[^.]{0,120}(?:for convenience|without cause|for any reason)|for convenience[^.]{0,60}(?:upon|on|by giving|with)[^.]{0,30}\d+\s*days", ttxt, re.I):
            put("termination_for_convenience", True, 0.9, tc)
        elif (hits := __import__("app.kcc", fromlist=["x"]).sentence_hits("termination_for_convenience", d.flat)):
            put("termination_for_convenience", True, 0.7, tc)           # a sentence that gives a party the right to terminate without cause / for convenience / on notice (shared with the clause detector)
        else:
            put("termination_for_convenience", None, 0.4, tc)
    # ---- governing law
    if not amend:
        gl = _governing_law(d.flat)
        if gl:
            put("governing_law", gl, 0.9, None)
        else:
            m, gc = d.search(r"(?:governed by|construed in accordance with|subject to)[^.]{0,50}?laws? of (?:the )?(?:State of |Commonwealth of |Republic of )?((?:England and Wales|Northern Ireland|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}))(?:,|\.| without| and | excluding| including| applicable| for| \(|;)", ("governing_law",), flags=0)
            if not m:     # real contracts: longer wording between 'governed by' and the jurisdiction, 'internal laws', or only 'the laws of the State of X'
                m, gc = d.search(r"(?:governed|construed|interpreted|enforced)[^.]{0,200}?(?:internal )?laws? (?:of|in) (?:the )?(?:State of |Commonwealth of |Province of |Republic of )?((?:England and Wales|Northern Ireland|[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,2}))(?:,|\.| without| and | excluding| including| applicable| for| \(|;| applied| regardless| as )", ("governing_law",), flags=0) or (None, None)
            if not m:
                m2 = re.search(r"laws? of (?:the )?(?:State|Commonwealth|Province) of ([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", d.flat)
                m, gc = (m2, None) if m2 else (None, None)
            if not m:     # countries and regions: 'laws of England', 'the laws of the People's Republic of China', 'laws of Hong Kong'
                m2 = re.search(r"(?:governed|construed|interpreted)[^.]{0,200}?laws? of (?:the )?((?:People[’']s Republic of China|Republic of [A-Z][a-z]+|England(?: and Wales)?|Hong Kong|Singapore|Japan|Germany|France|Switzerland|India|Australia|Canada|Ireland|Scotland|Netherlands|Israel|Ontario|British Columbia|Quebec|Belgium|Sweden|Italy|Spain|Brazil|Mexico|China|Korea|United Kingdom|Cayman Islands|Bermuda)\b)", d.flat)
                m, gc = (m2, None) if m2 else (None, None)
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


def _cells(line: str, labels: str) -> list[str]:
    """Split a table-like line into per-column values: '| Name: A | Name: B |', 'Name   A   B', 'Name: A     Name: B'."""
    raw = line.strip()
    if "|" in raw:
        parts = [c for c in raw.strip("|").split("|")]
    elif len(re.findall(rf"(?:^|\s)(?:{labels})\s*:", raw, re.I)) >= 2:       # 'Name: A Name: B': columns collapsed to single spaces (OCR, plain-text export)
        parts = [x for x in re.split(rf"(?=(?:^|\s)(?:{labels})\s*:)", raw, flags=re.I) if x.strip()]
    else:
        parts = re.split(r"\s{3,}", raw)
    if len(parts) > 1 and re.fullmatch(rf"\W*(?:{labels})\W*", parts[0].strip(), re.I):
        parts = parts[1:]                                   # a bare label cell ('Name | A | B') is not a column
    out = []
    for c in parts:
        c = re.sub(rf"^\W*(?:{labels})\b\W*", "", c.strip(), flags=re.I).strip(" *_\\")
        out.append(c)
    return out


def signatures(d: Doc) -> tuple[tuple | None, tuple | None]:
    """(customer, supplier) -> (name, date | None) or None. Handles 'Signed ... by X, Title, on DATE' sentences, By/Name/Title/Date blocks,
    two-column signature tables (Markdown, Word, PDF layout) and unsigned blocks (blank Name)."""
    cm = customer_markers()
    tail = d.md[-7000:]
    res: dict[str, tuple] = {}
    for m in re.finditer(rf"(?i:signed|executed|countersigned)\b[^\n]{{0,60}}?(?i:for and on behalf of|on behalf of|for)\s+(?:the\s+)?(?P<party>[^\n]{{2,90}}?)\s+by\s+(?P<name>{NAME})\s*,\s*(?P<title>[^,\n]{{2,70}}?),?\s*(?i:on|dated)\s+(?P<date>[A-Za-z0-9,/ \-]{{6,24}})", tail):
        role = "customer" if any(k in m.group("party").lower() for k in cm + ["customer", "client"]) else "supplier"
        res.setdefault(role, (m.group("name").strip(), tu.first_date(m.group("date"))))
    lines = [re.sub(r"[*_`]", "", ln).rstrip() for ln in tail.splitlines()]
    is_name = re.compile(r"^\W*(?:Printed\s+Name|Signed\s+by|Name)\b", re.I)
    for i, ln in enumerate(lines):
        if not is_name.match(ln.strip()):
            continue
        names = _cells(ln, r"Printed\s+Name|Signed\s+by|Name")
        inline_date = None
        for k, n in enumerate(names):                    # 'Name: Anika Rao Title: Authorised Signatory Date: 16 October 2026' flattened onto one line
            mt = re.search(r"\s+(?:Title|Date|Signature)\b\s*:?", n or "")
            if mt:
                if k == 0 and (dm := re.search(r"Date\s*:?\s*([A-Za-z0-9,/ \-]{6,24})$", n)):
                    inline_date = tu.first_date(dm.group(1))
                names[k] = n[:mt.start()].strip()
        names = [n if re.fullmatch(NAME, n or "") else "" for n in names]
        if not any(names) and len(names) <= 1:
            continue
        dates: list[date | None] = [inline_date] + [None] * (len(names) - 1) if names else []
        for w in lines[i + 1:i + 7]:
            if re.match(r"^\W*Date\b", w.strip(), re.I):
                cells = _cells(w, r"Date(?: signed)?")
                if len(cells) == 1 and len([d for _, d in tu.find_dates(cells[0])]) >= 2:      # columns collapsed by OCR / text extraction: 'September 18, 2026 September 21, 2026'
                    ds = [d for _, d in tu.find_dates(cells[0])][:2]
                    if len(names) == 1 and len(names[0].split()) in (4, 6):                       # '... Helena Cruz Grace Mbeki' -> two signatories
                        w_ = names[0].split()
                        names = [" ".join(w_[:len(w_) // 2]), " ".join(w_[len(w_) // 2:])]
                    dates = ds + [None] * (len(names) - 2)
                else:
                    dates = [tu.first_date(c) for c in cells][:len(names)] + [None] * (len(names) - len(cells))
                break
        hdr_lines: list[str] = []
        for w in reversed(lines[max(0, i - 10):i]):          # the header of this signature block only (stop at the previous heading / long paragraph)
            if w.lstrip().startswith("#") or len(w) > 170:
                break
            hdr_lines.insert(0, w)
        before = " ".join(hdr_lines).lower()
        if len(names) == 1:                              # a single block: only the nearest heading says whose it is
            before = " ".join(hdr_lines[-2:]).lower()
        cpos = min([before.find(k) for k in cm + ["customer", "client"] if before.find(k) >= 0] or [10**9])
        header = " ".join(hdr_lines)
        others = [m.start() for m in COMPANY_RX.finditer(header) if not any(k in m.group(0).lower() for k in cm)]
        spos = min([p for p in [before.find("supplier"), before.find("vendor"), before.find("provider")] + [o for o in others] if p >= 0] or [10**9])
        for ln_ in reversed(hdr_lines):                  # the line carrying our company: text after it = the other column's wrapped name, so ours is the first column
            low = ln_.lower()
            km = [(low.find(k), k) for k in cm if low.find(k) >= 0]
            if km and "|" not in ln_:                       # (markdown table rows keep their own, reliable header order)
                pos, k = min(km)
                cells_ = [c for c in re.split(r"\s{3,}|\|", ln_.strip()) if c.strip()]
                if len(cells_) > 2 and not COMPANY_RX.search(cells_[0]) and not any(x in cells_[0].lower() for x in cm):
                    cells_ = cells_[1:]                      # a row label ('Party', 'Company') is not a column
                ci = next((n for n, c in enumerate(cells_) if k in c.lower()), 0)
                mm = COMPANY_RX.search(ln_[pos:])
                tail = ln_[pos + mm.end():].strip(" |") if mm and len(names) > 1 else ""
                if len(cells_) > 1 and ci > 0:
                    cpos, spos = 10**8, 0
                elif len(cells_) > 1 or tail:
                    cpos, spos = 0, 10**8
                break
        tag_c, tag_s = before.find("(customer)"), before.find("(supplier)")
        if tag_c >= 0 and tag_s >= 0:                    # 'Vantage Telecom Services Inc (Supplier)   Arcadia Retail Inc. (Customer)'
            cpos, spos = tag_c, tag_s
        if cpos == 10**9 and spos == 10**9:
            order = ["customer", "supplier"]
        else:
            order = ["customer", "supplier"] if cpos <= spos else ["supplier", "customer"]
        if len(names) == 1:
            order = ["customer" if cpos < spos else "supplier"]
        for role, nm, dt_ in zip(order, names, dates):
            if nm:
                res.setdefault(role, (nm.strip(), dt_))
    return res.get("customer"), res.get("supplier")


COMPANY_RX = re.compile(r"[A-Z][\w&'\-]*(?:\s+(?:&\s+)?[A-Z][\w&'\-]*){0,5}?\s+(?:Inc\.?|LLC|LLP|Ltd\.?|Limited|Corp\.?|Corporation|Pte Ltd|GmbH|PLC|LP|Group|Co\.)")


US_STATES = ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine",
             "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota",
             "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming"]
PLACES = ["England and Wales", "England", "Scotland", "Ireland", "Northern Ireland", "Hong Kong", "Singapore", "Japan", "Germany", "France", "Switzerland", "India", "Australia", "Canada", "Ontario", "British Columbia", "Quebec",
          "Alberta", "Netherlands", "Israel", "Belgium", "Sweden", "Italy", "Spain", "Brazil", "Mexico", "China", "Korea", "United Kingdom", "Cayman Islands", "Bermuda", "Luxembourg", "Denmark", "Norway", "Finland", "Austria",
          "New Zealand", "South Africa", "United Arab Emirates", "Taiwan", "Thailand", "Malaysia", "Philippines", "District of Columbia"]
ALIASES = {"PRC": "People's Republic of China", "P.R.C.": "People's Republic of China", "UK": "United Kingdom", "U.K.": "United Kingdom"}


def _governing_law(flat: str) -> str | None:
    """The jurisdiction named in the sentence that says what law governs the agreement. Sentence first (a stray 'construed' elsewhere is not a governing-law clause), then the name in it:
    'State of X', 'laws of the People's Republic of China', 'internal laws of New York', or a known state / country."""
    sents = re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", flat))
    pri = [s for s in sents if re.search(r"\bgovern\w*\b[^.;]{0,160}\blaws?\b|\blaws?\b[^.;]{0,120}\bgovern\w*|governing law|(?:construed|interpreted|enforced)[^.;]{0,80}(?:in accordance with|under|pursuant to)[^.;]{0,40}\blaws?\b|\bapplicable law:|choice of law|laws? of (?:the )?state of", s, re.I)]
    for s in pri:
        k = re.search(r"govern\w*|laws? of|construed|interpreted|applicable law", s, re.I)
        tail = s[k.start():] if k else s
        best = None
        for name in US_STATES + PLACES + list(ALIASES) + ["People's Republic of China", "People’s Republic of China"]:
            mm = re.search(rf"(?<![A-Za-z]){re.escape(name)}(?![A-Za-z])", tail)
            if mm and (best is None or mm.start() < best[0]):
                best = (mm.start(), ALIASES.get(name, name.replace("’", "'")))
        if best:
            return best[1]
    return None
