"""Contracts held in the simulated procurement systems (Coupa, SAP, Ariba): fictional agreements with vendors that are not in the repository yet, written as documents (Word) with the same
terms the system's own metadata states, so a pull can be cross-checked: the dates and parties the pipeline reads from the document must equal what the ERP record says.
Dates are relative to today, so the demo is always current. Demo / test fixtures only."""
from __future__ import annotations

from datetime import date, timedelta

CUSTOMER = "Arcadia Retail Inc."


def add_months(d: date, n: int) -> date:
    m0 = d.month - 1 + n
    y, m = d.year + m0 // 12, m0 % 12 + 1
    for day in (d.day, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def _sig(vendor: str, eff: date, who: tuple[str, str]) -> str:
    return (f"\n## 12. Signatures\n\n| | **Customer** | **Supplier** |\n|---|---|---|\n| **Party** | {CUSTOMER} | {vendor} |\n| **Signed by** | Helena Cruz | {who[0]} |\n"
            f"| **Title** | VP Technology Sourcing | {who[1]} |\n| **Date** | {(eff - timedelta(days=6)):%B %d, %Y} | {(eff - timedelta(days=3)):%B %d, %Y} |\n")


def _body(kind: str, vendor: str, eff: date, months: int, pay: int, cap: float | None, tfc: int | None, law: str, renew_notice: int | None, annual: int | None, who: tuple[str, str]) -> str:
    end = add_months(eff, months)
    title = {"MSA": "Master Services Agreement", "NDA": "Mutual Non-Disclosure Agreement", "SaaS": "Software as a Service Agreement", "SOW": "Statement of Work No. 1", "WO": "Work Order No. 1"}[kind]
    parts = [f"# {title} – {vendor}\n", f"This {title} is made as of {eff:%d %B %Y} (the \"Effective Date\") between {CUSTOMER} (the \"Customer\") and {vendor} (the \"Supplier\").\n",
             f"## 1. Term\n\nThis Agreement commences on {eff:%d %B %Y} and continues for {months} months until {end:%d %B %Y}"
             + (f", and then renews automatically for successive 12-month periods unless either party gives not less than {renew_notice} days' written notice of non-renewal before the end of the then-current term.\n" if renew_notice else ".\n")]
    if kind != "NDA":
        parts += [f"## 2. Fees and Payment\n\n" + (f"The annual fees are USD {annual:,}. " if annual else "") + f"The Customer shall pay undisputed invoices within {pay} days of receipt of a valid invoice.\n"]
    if kind == "NDA":
        parts += ["## 2. Confidentiality\n\nEach party shall keep the other's Confidential Information confidential, use it only for the purpose of this Agreement, and these obligations survive for 3 years after this Agreement ends.\n"]
    else:
        parts += ["## 3. Confidentiality\n\nEach party shall keep the other's Confidential Information confidential and these obligations survive for 3 years after this Agreement ends.\n"]
    if cap is not None:
        parts += [f"## 4. Limitation of Liability\n\nEach party's aggregate liability under this Agreement shall not exceed {cap:g} times the annual fees paid or payable.\n"]
    if tfc:
        parts += [f"## 5. Termination\n\nThe Customer may terminate this Agreement without cause on {tfc} days' written notice to the Supplier. Either party may terminate for the other's material breach that remains uncured 30 days after written notice.\n"]
    elif kind != "NDA":
        parts += ["## 5. Termination\n\nEither party may terminate for the other's material breach that remains uncured 30 days after written notice. Neither party may terminate this Agreement for convenience.\n"]
    parts += [f"## 6. Governing Law\n\nThis Agreement is governed by the laws of {law}, and the parties submit to the courts of {law}.\n"]
    return "\n".join(parts) + _sig(vendor, eff, who)


def erp_contracts(today: date | None = None) -> list[dict]:
    today = today or date.today()
    spec = [  # system, id, kind, vendor, days since effective, months, pay, cap, tfc, law, renew notice, annual, signer
        ("coupa", 7101, "SaaS", "Brightwave Logistics Ltd", 40, 24, 45, 1.0, 60, "New York", 90, 360000, ("Ravi Menon", "Chief Revenue Officer")),
        ("coupa", 7102, "NDA", "Northgate Analytics Inc", 25, 36, 0, None, None, "Delaware", None, None, ("Elena Voss", "Authorised Signatory")),
        ("sap", 8201, "MSA", "Pinecrest Facilities Services LLC", 200, 36, 30, 2.0, 90, "Texas", None, None, ("Tom Hale", "Managing Director")),
        ("sap", 8202, "SOW", "Pinecrest Facilities Services LLC", 60, 10, 30, None, 30, "Texas", None, 540000, ("Tom Hale", "Managing Director")),
        ("ariba", 9301, "SaaS", "Quantum Ledger Systems Inc", 350, 12, 60, 1.0, None, "California", 60, 144000, ("Mia Zhou", "VP Sales")),
        ("ariba", 9302, "NDA", "Harbor Point Security LLP", 15, 24, 0, None, None, "New York", None, None, ("Greg Dunn", "Partner")),
    ]
    out = []
    for system, cid, kind, vendor, ago, months, pay, cap, tfc, law, rn, annual, who in spec:
        eff = today - timedelta(days=ago)
        end = add_months(eff, months)
        name = {"MSA": "Master Services Agreement", "NDA": "Mutual NDA", "SaaS": "SaaS Subscription Agreement", "SOW": "Statement of Work No. 1"}[kind]
        out.append({"system": system, "id": cid, "kind": kind, "vendor": vendor, "name": f"{name} – {vendor}", "start": eff, "end": end, "status": "active" if end >= today else "expired",
                    "filename": f"{vendor.split()[0].lower()}_{kind.lower()}.docx", "annual_value": annual, "payment_terms_days": pay or None, "auto_renew": bool(rn), "md": _body(kind, vendor, eff, months, pay, cap, tfc, law, rn, annual, who)})
    return out
