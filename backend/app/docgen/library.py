"""Clause library, deviation variants and template definitions for the fictional document set.

Single source of truth: templates, executed contracts and vendor drafts are all rendered from
this library, so planted deviations and ground-truth labels cannot drift from the text.
"""

from __future__ import annotations

from dataclasses import dataclass, field

CUSTOMER = "Seabright Hotels & Resorts Ltd" if __import__("os").environ.get("STANDARDS", "").lower() == "hotel" else "Arcadia Retail Inc."

# Standard (template) values for every placeholder used in clause text.
STD: dict[str, str | int] = dict(
    payment_terms_days=45,
    tfc_notice_days=30,
    cap="1",
    governing_law="New York",
    venue="New York County",
    conf_period="3 years",
    sla="99.9",
    sec_hours=48,
    breach_hours=48,
    audit_notice=14,
    audit_freq="once per year",
    cure_days=30,
    accept_days=10,
    warranty_days=90,
    insurance_cover="USD 5,000,000",
    fm_days=60,
    kp_days=15,
)


if __import__("os").environ.get("STANDARDS", "").lower() == "hotel":      # the hotel group's house standards (STANDARDS=hotel): the same templates, with its own values
    STD.update(governing_law="England and Wales", venue="London", tfc_notice_days=60, cap="1", sec_hours=24, breach_hours=24, insurance_cover="USD 5,000,000", audit_freq="once per year")


@dataclass(frozen=True)
class ClauseDef:
    ctype: str
    heading: str
    text: str
    playbook: str = ""
    fallback: str = ""
    severity_if_missing: str = "medium"
    variable: bool = False  # contract-specific by design (dates, fees, scope): never a deviation
    by_doc: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Variant:
    name: str
    severity: str  # low | medium | high | critical
    summary: str
    ctx: dict = field(default_factory=dict)
    text: str | None = None
    fields: dict = field(default_factory=dict)  # label fields this variant changes


C = ClauseDef
CLAUSES: dict[str, ClauseDef] = {
    c.ctype: c
    for c in [
        C(
            "term",
            "Term",
            "This {doc} commences on {effective_date} and, unless terminated earlier in "
            "accordance with its terms, expires on {expiry_date}.",
            variable=True,
        ),
        C(
            "renewal",
            "Renewal",
            "This {doc} does not renew automatically. Any extension requires a "
            "written agreement signed by both parties.",
            "Prefer no auto-renewal. If accepted, require a notice window of at least 90 days and cap "
            "any renewal price increase at 5%.",
            "This {doc} renews for successive 12-month periods unless either party gives at least 90 "
            "days' written notice of non-renewal.",
            "medium",
        ),
        C(
            "fees",
            "Fees",
            "The annual fees under this {doc} are USD {annual_value} and the total "
            "contract value is USD {total_value}, exclusive of applicable taxes.",
            variable=True,
            by_doc={
                "Work Order": "The fixed fee for this Work Order is USD {total_value}, exclusive "
                "of applicable taxes."
            },
        ),
        C("execution", "Execution", "{execution_text}", variable=True),
        C("scope", "Scope", "{scope_text}", variable=True),
        C("data_scope", "Data Scope", "{data_scope_text}", variable=True),
        C(
            "dpa_reference",
            "Data Processing Agreement",
            "The parties executed a Data Processing "
            "Agreement dated {dpa_date} covering the personal data processed under this {doc}.",
            variable=True,
        ),
        C(
            "payment",
            "Payment",
            "The Customer shall pay undisputed invoices within {payment_terms_days} "
            "days of receipt of a valid invoice. Late payment interest shall not exceed 1% per month.",
            "Standard is 45 days from receipt of a valid invoice. Fallback: 30 days. Never accept "
            "terms shorter than 30 days or advance payment beyond one quarter.",
            "The Customer shall pay undisputed invoices within 30 days of receipt of a valid invoice.",
            "medium",
        ),
        C(
            "termination_for_convenience",
            "Termination for Convenience",
            "The Customer may terminate "
            "this {doc} for convenience at any time by giving {tfc_notice_days} days' written notice to "
            "the Supplier, without penalty.",
            "The Customer must keep termination for convenience on 30 days' notice with no early "
            "termination fees.",
            "The Customer may terminate for convenience on 90 days' notice after an initial 12-month "
            "period.",
            "high",
        ),
        C(
            "termination_for_cause",
            "Termination for Cause",
            "Either party may terminate this {doc} by "
            "written notice if the other party commits a material breach that is not remedied within "
            "{cure_days} days of notice.",
            "Mutual termination for uncured material breach, 30-day cure.",
            "",
            "medium",
        ),
        C(
            "liability_cap",
            "Limitation of Liability",
            "Each party's total aggregate liability arising "
            "under this {doc} shall not exceed {cap} times the annual fees paid or payable.",
            "Standard is a mutual cap of 1x annual fees. Fallback: up to 2x. Uncapped liability must "
            "not be accepted other than for fraud, IP infringement indemnity and breach of "
            "confidentiality.",
            "Each party's total aggregate liability shall not exceed 2 times the annual fees paid or "
            "payable.",
            "high",
            by_doc={
                "SOW": "Liability under this SOW is governed by the liability provisions of the "
                "MSA."
            },
        ),
        C(
            "indemnity",
            "Indemnity",
            "The Supplier shall indemnify the Customer against third-party "
            "claims arising from the Supplier's breach of law, infringement of intellectual property "
            "rights, or gross negligence.",
            "Supplier indemnity for IP infringement, breach of law and gross negligence is mandatory.",
            "Gross negligence may be excluded only if the indemnity cap is at least 2x annual fees.",
            "high",
        ),
        C(
            "ip_ownership",
            "Intellectual Property",
            "The Customer owns all Customer Data and all "
            "deliverables created specifically for the Customer. The Supplier retains ownership of its "
            "pre-existing tools and grants the Customer a perpetual licence to use them within the "
            "deliverables.",
            "Customer must own bespoke deliverables and Customer Data.",
            "Supplier may own generic tooling if the Customer receives a perpetual licence.",
            "high",
        ),
        C(
            "confidentiality",
            "Confidentiality",
            "Each party shall keep the other party's Confidential "
            "Information confidential, use it only for the purposes of this {doc}, and continue to do "
            "so for {conf_period} after the {doc} ends.",
            "Confidentiality survives for at least 3 years after the end of the agreement.",
            "Minimum 2 years, with trade secrets protected indefinitely.",
            "high",
        ),
        C(
            "data_protection",
            "Data Protection",
            "The Supplier shall process personal data only on the "
            "Customer's documented instructions and in accordance with applicable data protection law. "
            "A Data Processing Agreement must be executed before any personal data is processed.",
            "Any vendor processing personal or guest data must sign the " + CUSTOMER.split()[0] + " DPA before go-live.",
            "",
            "critical",
            by_doc={
                "DPA": "The Supplier shall process personal data only on the Customer's documented "
                "instructions and only for the purposes stated in this DPA."
            },
        ),
        C(
            "audit_rights",
            "Audit Rights",
            "The Customer may audit the Supplier's records and "
            "facilities relevant to this {doc} {audit_freq} on {audit_notice} days' notice.",
            "Annual audit right on 14 days' notice.",
            "Audit once every two years.",
            "medium",
        ),
        C(
            "assignment",
            "Assignment",
            "Neither party may assign this {doc} without the other party's "
            "prior written consent, which shall not be unreasonably withheld.",
            "No assignment without consent.",
            "Assignment to a group company with notice.",
            "medium",
        ),
        C(
            "non_solicit",
            "Non-Solicitation",
            "Neither party shall solicit for employment the other "
            "party's personnel involved in the services during the term and for 12 months afterwards.",
            "Mutual 12-month non-solicitation.",
            "",
            "low",
        ),
        C(
            "governing_law",
            "Governing Law",
            "This {doc} is governed by the laws of {governing_law}. "
            "The courts at {venue} have exclusive jurisdiction.",
            "New York law and courts in New York County.",
            "Neutral law only with Legal approval.",
            "medium",
        ),
        C(
            "sla",
            "Service Levels",
            "The Supplier shall achieve at least {sla}% availability each "
            "month and shall issue service credits of 5% of monthly fees for each full 1% shortfall.",
            "99.9% availability with service credits.",
            "99.5% availability with service credits.",
            "high",
            by_doc={
                "SOW": "The Supplier shall meet the service levels stated in this SOW and shall "
                "credit 5% of monthly fees for each service level missed."
            },
        ),
        C(
            "security",
            "Information Security",
            "The Supplier shall maintain security controls aligned "
            "to ISO 27001 and shall notify the Customer of any security incident within {sec_hours} "
            "hours of becoming aware.",
            "ISO 27001-aligned controls; incident notice within 48 hours.",
            "Incident notice within 72 hours.",
            "high",
        ),
        C(
            "data_return",
            "Return of Data",
            "On termination or expiry, the Supplier shall return or "
            "securely delete all Customer Data within 30 days and certify the deletion in writing.",
            "Return or delete all data within 30 days with written certification.",
            "",
            "high",
        ),
        C(
            "acceptance",
            "Acceptance",
            "A deliverable is accepted only when the Customer confirms "
            "acceptance in writing after not less than {accept_days} business days of testing.",
            "Written acceptance after testing; no deemed acceptance.",
            "Deemed acceptance after 15 " "business days of silence.",
            "medium",
        ),
        C(
            "change_control",
            "Change Control",
            "Any change to the scope, timeline or fees requires a "
            "written change request signed by both parties.",
            "Written change requests only.",
            "",
            "low",
        ),
        C(
            "subprocessors",
            "Sub-processors",
            "The Supplier shall not appoint sub-processors without "
            "the Customer's prior written authorisation and remains liable for their acts and "
            "omissions.",
            "Prior written authorisation for every sub-processor.",
            "General authorisation with 30 days' notice and a right to object.",
            "high",
        ),
        C(
            "breach_notification",
            "Breach Notification",
            "The Supplier shall notify the Customer of "
            "any personal data breach within {breach_hours} hours of becoming aware.",
            "Notify within 48 hours.",
            "Notify within 72 hours.",
            "critical",
        ),
        C(
            "cross_border",
            "Cross-Border Transfers",
            "The Supplier shall not transfer personal data "
            "outside the United States without the Customer's prior written consent.",
            "No transfers outside the United States without consent.",
            "",
            "critical",
        ),
        C(
            "return_info",
            "Return of Information",
            "On request, each party shall promptly return or "
            "destroy the other party's Confidential Information and confirm destruction in writing.",
            "Return or destroy on request with written confirmation.",
            "",
            "medium",
        ),
        C(
            "services",
            "Services",
            "The Supplier shall provide the services described in each Statement of Work signed "
            "under this {doc} with reasonable skill and care, using suitably qualified personnel.",
            "Services are procured only through signed Statements of Work and Work Orders.",
            "",
            "medium",
        ),
        C(
            "order_of_precedence",
            "Order of Precedence",
            "If there is a conflict, the terms of this {doc} prevail over any Statement of Work, "
            "and a Statement of Work prevails over any Work Order, unless the later document "
            "expressly and specifically overrides a named clause of this {doc}.",
            "The MSA must prevail over SOWs and Work Orders; lower documents may not dilute MSA "
            "liability, IP, data protection or audit terms.",
            "",
            "high",
            by_doc={
                "SOW": "This {doc} is issued under, and governed by, the Master Services Agreement. "
                "If there is a conflict, the Master Services Agreement prevails over this {doc}. "
                "The liability, indemnity, intellectual property, confidentiality, data protection, "
                "audit and governing law terms of the Master Services Agreement apply to this {doc}.",
                "Work Order": "This {doc} is issued under the Statement of Work and the Master "
                "Services Agreement named above. If there is a conflict, the Master Services "
                "Agreement prevails, then the Statement of Work, then this {doc}.",
            },
        ),
        C(
            "warranties",
            "Warranties",
            "The Supplier warrants that the services will be performed with reasonable skill and "
            "care and will conform to the applicable Statement of Work, and shall correct any "
            "non-conforming services free of charge for {warranty_days} days after acceptance.",
            "90-day warranty with free re-performance; no blanket disclaimers.",
            "A 60-day warranty period.",
            "medium",
        ),
        C(
            "insurance",
            "Insurance",
            "The Supplier shall maintain professional indemnity and commercial general liability "
            "insurance of at least {insurance_cover} per claim throughout the term and provide "
            "certificates on request.",
            "Minimum USD 5 million per claim.",
            "USD 2 million per claim for engagements under USD 1 million a year.",
            "medium",
        ),
        C(
            "force_majeure",
            "Force Majeure",
            "Neither party is liable for delay caused by events beyond its reasonable control, "
            "provided it notifies the other promptly and uses reasonable efforts to resume "
            "performance. Either party may terminate the affected services if the event continues "
            "for more than {fm_days} days.",
            "Narrow force majeure: supplier staffing and subcontractor failures are not force "
            "majeure; termination right after 60 days.",
            "Termination right after 90 days.",
            "medium",
        ),
        C(
            "dispute_resolution",
            "Dispute Resolution",
            "Disputes shall first be escalated to the parties' senior management for resolution "
            "within 15 days, and then referred to mediation before either party commences court "
            "proceedings.",
            "Escalate, then mediate, then New York courts. Foreign arbitration needs Legal approval.",
            "",
            "low",
        ),
        C(
            "key_personnel",
            "Key Personnel",
            "The Supplier shall assign the key personnel named in this {doc} and shall not replace "
            "them without the Customer's prior written consent, and shall provide a replacement of "
            "equivalent skill within {kp_days} days of any departure.",
            "Named key personnel; replacement only with consent and equal or better skill.",
            "Replacement on 15 days' notice with a handover.",
            "medium",
        ),
        C(
            "governance",
            "Governance and Reporting",
            "The parties shall hold a monthly service review meeting, and the Supplier shall "
            "provide a written monthly report of progress against milestones and service levels.",
            "Monthly governance meeting and written report.",
            "",
            "low",
        ),
        C("msa_reference", "Master Agreement Reference", "{msa_reference_text}", variable=True),
        C("sow_reference", "Statement of Work Reference", "{sow_reference_text}", variable=True),
        C("deliverables", "Deliverables and Milestones", "{deliverables_text}", variable=True),
    ]
}
HEADING_TO_TYPE = {c.heading: c.ctype for c in CLAUSES.values()}


def V(name, sev, summary, **kw) -> Variant:
    return Variant(name, sev, summary, **kw)


VARIANTS: dict[str, dict[str, Variant]] = {
    "renewal": {
        "auto": V(
            "auto",
            "medium",
            "Auto-renews for 12-month periods; the Customer must give notice to exit",
            text="This {doc} renews automatically for successive periods of 12 months unless either "
            "party gives at least {notice_period_days} days' written notice of non-renewal before "
            "the end of the then-current term.",
            fields={"auto_renew": True},
        )
    },
    "payment": {
        "net30": V(
            "net30",
            "low",
            "Payment terms shortened to 30 days (within fallback)",
            ctx={"payment_terms_days": 30},
            fields={"payment_terms_days": 30},
        ),
        "net15": V(
            "net15",
            "high",
            "Payment terms shortened to 15 days (below fallback)",
            ctx={"payment_terms_days": 15},
            fields={"payment_terms_days": 15},
        ),
    },
    "termination_for_convenience": {
        "none": V(
            "none",
            "high",
            "No right to terminate for convenience",
            text="Neither party "
            "may terminate this {doc} for convenience. The {doc} may be terminated only "
            "for cause.",
            fields={"termination_for_convenience": False},
        ),
        "long": V(
            "long",
            "medium",
            "Termination for convenience needs 180 days' notice plus fees",
            text="The Customer may terminate this {doc} for convenience by giving 180 "
            "days' written notice and paying all fees for the notice period.",
            fields={"termination_for_convenience": True},
        ),
    },
    "liability_cap": {
        "x2": V(
            "x2",
            "low",
            "Liability cap raised to 2x annual fees (within fallback)",
            ctx={"cap": "2"},
            fields={"liability_cap_multiple": 2.0},
        ),
        "x05": V(
            "x05",
            "high",
            "Liability cap lowered to 0.5x annual fees",
            ctx={"cap": "0.5"},
            fields={"liability_cap_multiple": 0.5},
        ),
        "unlimited": V(
            "unlimited",
            "critical",
            "Liability is unlimited, including indirect and " "consequential loss",
            text="Each party's liability under this {doc} is "
            "unlimited, including liability for indirect and consequential losses.",
            fields={"liability_cap_multiple": None, "liability_cap_text": "Unlimited"},
        ),
    },
    "indemnity": {
        "one_way": V(
            "one_way",
            "high",
            "Indemnity runs from the Customer to the Supplier",
            text="The Customer shall indemnify the Supplier against all third-party "
            "claims arising from the Customer's use of the services.",
        ),
        "no_ip": V(
            "no_ip",
            "high",
            "Supplier IP infringement indemnity is excluded",
            text="The Supplier shall indemnify the Customer against third-party claims "
            "arising from the Supplier's breach of law. Infringement claims are excluded.",
        ),
    },
    "ip_ownership": {
        "supplier": V(
            "supplier",
            "high",
            "Supplier owns deliverables; Customer gets a limited licence",
            text="The Supplier owns all deliverables and work product and grants the Customer a "
            "limited, non-transferable licence to use them during the term.",
        )
    },
    "confidentiality": {
        "short": V(
            "short",
            "medium",
            "Confidentiality survives only 1 year (standard: 3 years)",
            ctx={"conf_period": "1 year"},
        )
    },
    "data_protection": {
        "weak": V(
            "weak",
            "critical",
            "Supplier may process personal data at its own discretion",
            text="The Supplier may process personal data in the manner it considers appropriate to "
            "provide and improve its services.",
        )
    },
    "audit_rights": {
        "none": V(
            "none",
            "medium",
            "No audit right",
            text="The Customer has no right to audit " "the Supplier.",
        ),
        "every3": V(
            "every3",
            "low",
            "Audit allowed only once every three years",
            ctx={"audit_freq": "once every three years"},
        ),
    },
    "assignment": {
        "free": V(
            "free",
            "medium",
            "Supplier may assign without consent",
            text="The Supplier may assign "
            "this {doc} to any affiliate or successor without the Customer's consent.",
        )
    },
    "governing_law": {
        "england": V(
            "england",
            "medium",
            "Governed by English law (standard: New York law)",
            ctx={"governing_law": "England and Wales", "venue": "London"},
            fields={"governing_law": "England and Wales"},
        ),
        "singapore": V(
            "singapore",
            "medium",
            "Governed by Singapore law (standard: New York law)",
            ctx={"governing_law": "Singapore", "venue": "Singapore"},
            fields={"governing_law": "Singapore"},
        ),
        "india": V(
            "india",
            "medium",
            "Governed by Indian law (standard: New York law)",
            ctx={"governing_law": "India", "venue": "Mumbai"},
            fields={"governing_law": "India"},
        ),
    },
    "sla": {
        "lower": V("lower", "low", "Availability commitment lowered to 99.5%", ctx={"sla": "99.5"}),
        "weak": V(
            "weak",
            "high",
            "Availability lowered to 99.0% and no service credits",
            text="The Supplier shall achieve at least 99.0% availability each month. No "
            "service credits apply.",
        ),
    },
    "security": {
        "slow": V(
            "slow",
            "medium",
            "Incident notice within 7 days (standard: 48 hours)",
            ctx={"sec_hours": "168"},
            text="The Supplier shall maintain security controls aligned to ISO "
            "27001 and shall notify the Customer of any security incident within "
            "7 days of becoming aware.",
        )
    },
    "acceptance": {
        "deemed": V(
            "deemed",
            "medium",
            "Deliverables deemed accepted after 3 days of silence",
            text="A deliverable is deemed accepted 3 days after delivery unless the Customer "
            "objects in writing.",
        )
    },
    "subprocessors": {
        "general": V(
            "general",
            "high",
            "Sub-processors may be appointed at the Supplier's discretion",
            text="The Supplier may appoint sub-processors at its discretion on notice to the "
            "Customer.",
        )
    },
    "breach_notification": {
        "slow5": V(
            "slow5",
            "high",
            "Breach notice within 5 days (standard: 48 hours)",
            text="The Supplier shall notify the Customer of any personal data breach "
            "within 5 days of becoming aware.",
        ),
        "h72": V(
            "h72",
            "medium",
            "Breach notice within 72 hours (standard: 48 hours)",
            ctx={"breach_hours": 72},
        ),
    },
    "cross_border": {
        "any": V(
            "any",
            "critical",
            "Personal data may be transferred to any country",
            text="The Supplier may transfer personal data to any country where it or its "
            "sub-processors operate.",
        )
    },
}

VARIANTS.update(
    {
        "warranties": {
            "short": V(
                "short", "medium", "Warranty period cut to 30 days (standard: 90)",
                ctx={"warranty_days": 30},
            ),
            "disclaim": V(
                "disclaim", "high", "All warranties disclaimed",
                text="The Supplier disclaims all warranties, express or implied, in relation to the "
                "services.",
            ),
        },
        "insurance": {
            "low": V(
                "low", "medium", "Insurance cover only USD 500,000 (standard: USD 5,000,000)",
                ctx={"insurance_cover": "USD 500,000"},
            )
        },
        "force_majeure": {
            "broad": V(
                "broad", "medium", "Supplier excused for subcontractor and staffing failures",
                text="The Supplier is excused from any delay or failure, including delay caused by "
                "its subcontractors or labour shortages, and the Customer has no right to "
                "terminate for force majeure.",
            )
        },
        "dispute_resolution": {
            "arbitration": V(
                "arbitration", "medium", "Disputes go to arbitration in London (standard: New York courts)",
                text="Disputes shall be finally settled by arbitration in London under the ICC "
                "rules, and the courts of England have no jurisdiction.",
            )
        },
        "order_of_precedence": {
            "sow_prevails": V(
                "sow_prevails", "high", "The SOW overrides the MSA in a conflict",
                text="In case of conflict, this {doc} prevails over the Master Services Agreement.",
            )
        },
        "key_personnel": {
            "free": V(
                "free", "medium", "Supplier may replace key personnel at any time without notice",
                text="The Supplier may replace any personnel at any time and without notice to the "
                "Customer.",
            )
        },
    }
)

TEMPLATES: dict[str, dict] = {
    # Typical enterprise templates. SOWs and Work Orders inherit from their parent agreement
    # (order_of_precedence + references) and are built on top of the MSA terms.
    "MSA": dict(
        name="Master Services Agreement",
        doc="Agreement",
        clauses=[
            "term",
            "renewal",
            "services",
            "order_of_precedence",
            "payment",
            "termination_for_convenience",
            "termination_for_cause",
            "warranties",
            "liability_cap",
            "indemnity",
            "insurance",
            "ip_ownership",
            "confidentiality",
            "data_protection",
            "audit_rights",
            "assignment",
            "force_majeure",
            "dispute_resolution",
            "non_solicit",
            "governing_law",
            "execution",
        ],
    ),
    "SOW": dict(
        name="Statement of Work",
        doc="SOW",
        clauses=[
            "msa_reference",
            "scope",
            "deliverables",
            "term",
            "fees",
            "payment",
            "key_personnel",
            "acceptance",
            "sla",
            "governance",
            "change_control",
            "order_of_precedence",
            "termination_for_convenience",
            "liability_cap",
            "execution",
        ],
    ),
    "WO": dict(
        name="Work Order",
        doc="Work Order",
        clauses=[
            "sow_reference",
            "scope",
            "deliverables",
            "term",
            "fees",
            "payment",
            "acceptance",
            "change_control",
            "order_of_precedence",
            "execution",
        ],
    ),
    "NDA": dict(
        name="Non-Disclosure Agreement",
        doc="NDA",
        clauses=[
            "term",
            "confidentiality",
            "return_info",
            "non_solicit",
            "governing_law",
            "execution",
        ],
    ),
    "SaaS": dict(
        name="SaaS Subscription Agreement",
        doc="Agreement",
        clauses=[
            "term",
            "renewal",
            "fees",
            "data_scope",
            "dpa_reference",
            "payment",
            "sla",
            "security",
            "data_protection",
            "data_return",
            "liability_cap",
            "termination_for_convenience",
            "ip_ownership",
            "confidentiality",
            "governing_law",
            "execution",
        ],
    ),
    "DPA": dict(
        name="Data Processing Agreement",
        doc="DPA",
        clauses=[
            "scope",
            "term",
            "data_protection",
            "subprocessors",
            "breach_notification",
            "cross_border",
            "audit_rights",
            "data_return",
            "governing_law",
            "execution",
        ],
    ),
}
# Columns of the key-clauses matrix (variable/deal-specific clauses excluded). `execution` means
# "signed by both parties".
KEY_CLAUSES = [
    "term", "renewal", "order_of_precedence", "payment", "termination_for_convenience",
    "termination_for_cause", "warranties", "liability_cap", "indemnity", "insurance",
    "ip_ownership", "confidentiality", "data_protection", "audit_rights", "assignment",
    "force_majeure", "dispute_resolution", "non_solicit", "governing_law", "sla", "security",
    "data_return", "execution",
]
OPTIONAL = {"dpa_reference"}  # present only when a DPA exists; not "missing" when absent


def clause_text(ctype: str, doc: str, ctx: dict | None = None, variant: str | None = None) -> str:
    """Render a clause. Standard values fill any placeholder not in ctx."""
    c = CLAUSES[ctype]
    v = VARIANTS.get(ctype, {}).get(variant) if variant else None
    base = v.text if v and v.text else c.by_doc.get(doc, c.text)
    merged = {**STD, "doc": doc, **(v.ctx if v else {}), **(ctx or {})}
    return base.format(**merged)


def standard_text(ctype: str, doc: str) -> str:
    """Template text with standard values (placeholders shown for variable clauses)."""
    ph = dict(
        effective_date="[Effective Date]",
        expiry_date="[Expiry Date]",
        annual_value="[amount]",
        total_value="[amount]",
        scope_text="[Scope of services]",
        data_scope_text="[Description of personal data processed, if any]",
        dpa_date="[date]",
        execution_text="[Signature blocks: Customer and Supplier signatories and dates]",
        msa_reference_text="[Reference to the governing Master Services Agreement and its date]",
        sow_reference_text="[Reference to the governing Statement of Work and Master Services Agreement]",
        deliverables_text="[Deliverables and milestones with dates and acceptance criteria]",
        notice_period_days="[notice]",
    )
    return clause_text(ctype, doc, ph)
