"""Who is the counterparty, what kind of document is it, which agreement does it sit under. Rules over the text of real contracts
(no sidecar needed); the sidecar and the folder (drafts/) only add what a text cannot say (owner, category, draft status)."""
from __future__ import annotations

import re
from datetime import date, timedelta

from sqlalchemy import text

from app import textutil as tu
from app.extract_rules import customer_markers

SUFFIX = r"(?i:Inc\.?|LLC|L\.L\.C\.|LLP|Ltd\.?|Limited|Corp\.?|Corporation|Pte\.? Ltd\.?|GmbH|PLC|LP|Co\.|Company|AG|S\.A\.|B\.V\.|Pty Ltd)(?![A-Za-z])"
COMPANY = re.compile(rf"([A-Z][\w&'\-]*(?:\s+(?:&\s+)?[A-Z][\w&'\-]*){{0,5}}?(?:\s+{SUFFIX}))")
TYPE_RULES = [(r"amendment", "Amendment"), (r"data (?:processing|protection) (?:agreement|addendum)|data processing", "DPA"), (r"non-?disclosure|confidentiality agreement|\bnda\b", "NDA"), (r"work order", "Work Order"),
              (r"statement of work|\bsow\b", "SOW"), (r"subscription|software as a service|\bsaas\b|order form|license and support|licence and support|master subscription", "SaaS"),
              (r"master services|master agreement|\bmsa\b|services agreement|framework agreement", "MSA")]
GENERIC_TITLE = re.compile(r"^(?:(?:mutual |draft )?(?:master (?:services|subscription) agreement|statement of work(?: no\.? ?\d+)?|work order(?: no\.? ?\d+)?|(?:mutual )?non-?disclosure agreement|data processing (?:agreement|addendum)|"
                           r"(?:software )?subscription agreement|services agreement|amendment(?: no\.? ?\d+)?(?: to [\w ]+)?|order form|software as a service agreement))$", re.I)


def vendor_short(v: str) -> str:
    return re.sub(rf"[\s,]+{SUFFIX}$", "", v.strip(), flags=re.I).strip(" ,.")


def clean_vendor(v: str) -> str:
    v = re.sub(r"\s+", " ", v).strip(" ,.;")
    while (v2 := re.sub(r"^(?:Supplier|Vendor|Provider|Contractor|Client|Customer|Party|Between|And|The)\s+", "", v)) != v:     # 'Customer Supplier Acme Ltd'
        v = v2
    if v.isupper():                              # 'TATVA INFOSYSTEMS LTD' -> 'Tatva Infosystems Ltd'
        v = " ".join(w if w in ("LLC", "LLP", "PLC", "LP", "AG", "GmbH") else w.capitalize() for w in v.split())
    return v


def _mask_customer(head: str, markers: list[str]) -> str:
    """Our own company's full name (it may contain '&' or 'and', e.g. 'Seabright Hotels & Resorts Ltd') is replaced by 'the Customer', so that its words are not read as the supplier."""
    for k in markers:
        head = re.sub(rf"(?:[A-Z][\w'’.-]*\s+(?:(?:&|and)\s+)?){{0,4}}(?i:\b{re.escape(k)}\b)(?:\s+(?:(?:&|and)\s+)?[A-Z][\w'’.-]*){{0,4}}?\s+(?:Inc\.?|Ltd\.?|LLC|LLP|PLC|Pte Ltd|Pte\. Ltd\.|Corp\.?|Corporation|Company|Co\.|Limited|GmbH|Group|Holdings)", "the Customer", head)
    return head


def find_vendor(md: str, header: dict, sidecar: dict) -> str | None:
    cm = customer_markers()
    if header.get("Parties"):
        m = re.search(r'and (.+?) \(the "Supplier"\)', header["Parties"])
        if m:
            return clean_vendor(m.group(1))
    head = re.sub(r"[*_`|]", " ", re.sub(r"<!--.*?-->", " ", md))[:2600]
    head = re.sub(r"\s+", " ", head.replace("\\&", "&").replace("&amp;", "&"))        # markdown / HTML escapes of an ampersand in a company name
    head = _mask_customer(head, cm)
    for rx in (r"(?:between|by and between|made between|entered into by and between)\s+(.{5,260}?)\s+(?:and|&)\s+(.{5,200})", r"(?:Supplier|Vendor|Provider|Contractor|Service Provider|Client|Counterparty)\s*[:|]\s*(.{4,120})"):
        m = re.search(rx, head, re.I)
        if not m:
            continue
        cands = []
        for g in (m.group(0),):          # whole span: a supplier name containing '&' must not be cut in two at the separator
            cands += [clean_vendor(c) for c in COMPANY.findall(g)]
        cands = [c for c in cands if not any(k in c.lower() for k in cm)]
        if cands:
            return cands[0]
    for c in COMPANY.findall(head):
        c = clean_vendor(c)
        if not any(k in c.lower() for k in cm) and c.lower() not in ("inc", "ltd"):
            return c
    return sidecar.get("vendor")


def find_type(title: str, md: str) -> str:
    t = title.lower()
    for rx, ty in TYPE_RULES:
        if re.search(rx, t):
            return ty
    first = re.sub(r"\s+", " ", md[:500]).lower()
    for rx, ty in TYPE_RULES:
        if re.search(rx, first):
            return ty
    return "MSA"


PARENT_TABLE_RX = re.compile(r"Parent (?:Agreement|Contract)\W{1,6}(?P<what>Master Services Agreement|Master Subscription Agreement|Master Agreement|Software[- ]as[- ]a[- ]Service Agreement|SaaS Agreement|Subscription Agreement|Services Agreement|Statement of Work(?:\s+(?:No\.?\s*)?\d+)?|SOW(?:\s+(?:No\.?\s*)?\d+)?)[^.]{0,40}?(?:dated|effective)(?:\s+as of)?\s+(?P<date>[A-Za-z0-9,/ .\-]{6,30})", re.I)
PARENT_RX = re.compile(r"(?:under|pursuant to|issued under|governed by|subject to|forms? part of|supplements?|amends?|amending|in connection with|to the|of the)\s+(?:the\s+)?(?:that certain\s+)?"
                       r"(?P<what>Master Services Agreement|Master Subscription Agreement|Master Agreement|Software[- ]as[- ]a[- ]Service Agreement|SaaS Agreement|Subscription Agreement|Services Agreement|MSA|Statement of Work(?:\s+(?:No\.?\s*)?\d+)?|SOW(?:\s+(?:No\.?\s*)?\d+)?|Work Order(?:\s+(?:No\.?\s*)?\d+)?)"
                       r"[^.]{0,80}?(?:dated|effective)(?:\s+as of)?\s+(?P<date>[A-Za-z0-9,/ .\-]{6,30})", re.I)
TYPE_OF = [(r"statement of work|^sow", "SOW"), (r"work order", "Work Order"), (r"subscription|saas|software[- ]as", "SaaS"), (r"master|services agreement|^msa", "MSA")]


def parent_ref(md: str, doc_type: str) -> dict | None:
    head = re.sub(r"\s+", " ", re.sub(r"[*_`|]", " ", re.sub(r"<!--.*?-->", " ", md)))[:3500]
    for m in list(PARENT_TABLE_RX.finditer(head)) + list(PARENT_RX.finditer(head)):
        what = m.group("what")
        ty = next((t for rx, t in TYPE_OF if re.search(rx, what, re.I)), None)
        if not ty or ty == doc_type and doc_type not in ("Amendment",):
            continue
        num = re.search(r"(\d+)\s*$", what)
        return {"type": ty, "date": (tu.first_date(m.group("date")) or None), "number": int(num.group(1)) if num else None}
    return None


def infer(md: str, header: dict, clauses: list[dict], sidecar: dict, folder_hint: str = "") -> dict:
    title = next((ln[2:].strip() for ln in md.splitlines() if ln.startswith("# ")), None) or "Untitled document"
    title = re.sub(r"\*+", "", title).strip()
    vendor = find_vendor(md, header, sidecar) or "Unknown vendor"
    dt = header.get("Document Type", "").strip() or find_type(title, md)
    if header.get("Amends"):
        dt = "Amendment"
    if dt not in ("MSA", "SOW", "Work Order", "NDA", "SaaS", "DPA", "Amendment"):
        dt = find_type(title, md)
    if GENERIC_TITLE.match(title) and vendor != "Unknown vendor":
        title = f"{title} – {vendor_short(vendor)}"
    ref = parent_ref(md, dt)
    status = sidecar.get("status") or ("draft" if re.search(r"(^|/)drafts?(/|$)", folder_hint) or re.search(r"^\s*(?:#\s*)?draft\b", title, re.I) else "active")
    return dict(title=title, vendor=vendor, type=dt, category=sidecar.get("category") or guess_category(md, dt), owner=sidecar.get("owner") or "Unassigned", status=status, parent_ref=ref)


CATEGORY_WORDS = [("Security", r"cyber|penetration|security operations|soc\b"), ("Cloud", r"hosting|colocation|cloud infrastructure|iaas|data cent"), ("Telecom", r"telecom|network|circuit|carrier|connectivity"),
                  ("Staffing", r"staffing|staff augmentation|contingent|recruit"), ("Marketing", r"marketing|advertis|campaign"), ("SaaS", r"subscription|saas|software as a service"), ("IT Services", r"implementation|consulting|application|systems integration|managed services")]


def guess_category(md: str, doc_type: str) -> str:
    low = md[:4000].lower()
    for cat, rx in CATEGORY_WORDS:
        if re.search(rx, low):
            return cat
    return "Uncategorised"


# ------------------------------------------------------------------ parent resolution
def _num_of(title: str) -> int | None:
    m = re.search(r"(?:no\.?|number|#|sow|work order)\s*(\d+)", title, re.I)
    return int(m.group(1)) if m else None


def resolve_parent(s, cid: int, ref) -> int | None:
    row = s.execute(text("SELECT type, vendor, effective_date, status FROM contracts WHERE id=:i"), {"i": cid}).first()
    if not row or (row[3] == "draft" and not ref):        # a draft is linked only when it names its parent
        return None
    typ, vendor, eff = row[0], row[1], row[2]
    if isinstance(ref, str) and ref:                       # an exact title (generated documents, sidecars)
        pid = s.execute(text("SELECT id FROM contracts WHERE title=:t AND id<>:i"), {"t": ref, "i": cid}).scalar()
        if pid:
            return pid
        ref = None
    cands = [dict(r) for r in s.execute(text("SELECT id, type, title, effective_date FROM contracts WHERE vendor=:v AND id<>:i AND status <> 'draft' ORDER BY effective_date"), {"v": vendor, "i": cid}).mappings()]
    if not cands:
        return None
    want = ref["type"] if ref else {"SOW": "MSA", "Work Order": "SOW", "Amendment": "MSA", "NDA": "MSA", "DPA": "SaaS"}.get(typ)
    if not want:
        return None
    order = [want] + [w for w in {"SOW": ["SaaS"], "Work Order": ["MSA", "SaaS"], "Amendment": ["SaaS", "SOW"], "NDA": ["SaaS"], "DPA": ["MSA"]}.get(typ, []) if w != want]
    for t in order:
        pool = [c for c in cands if c["type"] == t]
        if not pool:
            continue
        if ref and ref.get("date"):
            near = [c for c in pool if c["effective_date"] and abs((c["effective_date"] - ref["date"]).days) <= 5]
            if near:
                pool = near
        if ref and ref.get("number"):
            numbered = [c for c in pool if _num_of(c["title"]) == ref["number"]]
            pool = numbered or pool
        before = [c for c in pool if c["effective_date"] and eff and c["effective_date"] <= eff + timedelta(days=3)] or pool
        if len(before) == 1 or ref:
            return before[-1]["id"]
        if typ in ("NDA", "Amendment", "DPA") and len(pool) >= 1:
            return pool[-1]["id"] if typ != "NDA" else (pool[0]["id"] if len(pool) == 1 else None)
        return before[-1]["id"]
    return None


_ = date
