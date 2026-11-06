"""Specs for the executed contracts and vendor drafts: an enterprise IT-services portfolio for the
fictional customer Arcadia Retail Inc. (USD). Vendor names are fictional lookalikes of well-known
IT firms (a global systems integrator, a Big-4-style consultancy, an offshore IT services major,
a web-infrastructure software vendor) so the demo feels real without naming real companies.
Day offsets are relative to the seed date so the dashboard always looks current."""
from __future__ import annotations

K, M = 1_000, 1_000_000

ACC = "Accentia Technology Services Inc"   # global systems integrator
DEL = "Delmont Consulting LLP"             # Big-4-style consultancy
TAR = "Taraka Consultancy Services Ltd"    # offshore IT services major
NGX = "Nginova Systems Inc"                # web infrastructure / API gateway software
CIR, LED = "Cirrus CRM Inc", "Ledgerline Systems Inc"
PUL, ADS, SKY = "PulseHR Inc", "AdSpark Analytics LLP", "Skyguard Security Solutions Inc"

# eff/exp: day offsets from the seed date. dev: "clause_type:variant". amend: overridden clauses.
CONTRACTS: list[dict] = [
    dict(key="accentia_msa", title="Master Services Agreement – Accentia Technology Services",
         vendor=ACC, category="IT Services", type="MSA", template="MSA",
         owner="Jordan Blake (IT Procurement)", eff=-330, exp=420, auto=True, notice=90,
         dev=["renewal:auto", "audit_rights:every3"]),
    dict(key="accentia_sow1", title="SOW 1 – Application Managed Services – Accentia Technology Services",
         vendor=ACC, category="IT Services", type="SOW", template="SOW",
         owner="Jordan Blake (IT Procurement)", parent="accentia_msa", eff=-277, exp=88,
         annual=4_800 * K, total=9_600 * K,
         scope="24x7 application managed services (L2/L3) for Arcadia's e-commerce, merchandising "
         "and ERP platforms.", dev=["acceptance:deemed", "key_personnel:free"]),
    dict(key="accentia_sow2", title="SOW 2 – AWS Cloud Migration and Platform Engineering – Accentia Technology Services",
         vendor=ACC, category="Cloud", type="SOW", template="SOW", owner="Sam Ortiz (Infrastructure)",
         parent="accentia_msa", eff=-100, exp=400, annual=11_500 * K, total=23_000 * K,
         scope="Migration of 140 workloads to AWS, landing zone, FinOps and platform engineering.",
         dev=[]),
    dict(key="accentia_sow3", title="SOW 3 – Service Desk Staff Augmentation – Accentia Technology Services",
         vendor=ACC, category="Staffing", type="SOW", template="SOW",
         owner="Jordan Blake (IT Procurement)", parent="accentia_msa", eff=-339, exp=26,
         annual=2_400 * K, total=2_400 * K,
         scope="Twelve full-time service desk analysts supplied on a time-and-materials basis.",
         dev=["sla:weak"]),
    dict(key="accentia_amd1", title="Amendment No. 1 to MSA – Accentia Technology Services",
         vendor=ACC, category="IT Services", type="Amendment", template="MSA",
         owner="Jordan Blake (IT Procurement)", parent="accentia_msa", eff=-60, exp=700,
         amend=[("term", {}), ("payment", {"payment_terms_days": 30}), ("liability_cap", {"cap": "2"})]),
    dict(key="accentia_wo1", title="Work Order 1 – Data Center Exit Wave 2 – Accentia Technology Services",
         vendor=ACC, category="Cloud", type="Work Order", template="WO",
         owner="Sam Ortiz (Infrastructure)", parent="accentia_sow2", eff=-60, exp=380,
         total=1_200 * K, scope="Decommissioning of the secondary data center and migration of "
         "the remaining 38 servers to AWS.", dev=[]),
    dict(key="accentia_wo2", title="Work Order 2 – Endpoint Security Hardening – Accentia Technology Services",
         vendor=ACC, category="Security", type="Work Order", template="WO",
         owner="Taylor Reed (Security)", parent="accentia_sow2", eff=-20, exp=390, total=750 * K,
         scope="EDR rollout and CIS hardening of 6,500 store and corporate endpoints.",
         unsigned_supplier=True, dev=[]),  # planted: Supplier has not countersigned yet
    dict(key="accentia_nda", title="NDA – Accentia Technology Services", vendor=ACC,
         category="IT Services", type="NDA", template="NDA", owner="Jordan Blake (IT Procurement)",
         parent="accentia_msa", eff=-340, exp=400, dev=["confidentiality:short"]),

    dict(key="delmont_msa", title="Master Services Agreement – Delmont Consulting", vendor=DEL,
         category="Consulting", type="MSA", template="MSA", owner="Morgan Hayes (Finance Transformation)",
         eff=-400, exp=450, auto=False,
         dev=["liability_cap:unlimited", "termination_for_convenience:none", "governing_law:england",
              "indemnity:one_way", "insurance:low", "warranties:short"]),
    dict(key="delmont_sow1", title="SOW 1 – SAP S/4HANA Transformation, Phase 1 – Delmont Consulting",
         vendor=DEL, category="ERP", type="SOW", template="SOW",
         owner="Morgan Hayes (Finance Transformation)", parent="delmont_msa", eff=-303, exp=62,
         annual=7_200 * K, total=14_400 * K,
         scope="Phase 1 of the SAP S/4HANA finance and supply-chain transformation: design, build "
         "and data migration.", dev=["payment:net30", "order_of_precedence:sow_prevails"]),
    dict(key="delmont_sow2", title="SOW 2 – Cybersecurity Posture Assessment and Roadmap – Delmont Consulting",
         vendor=DEL, category="Security", type="SOW", template="SOW", owner="Taylor Reed (Security)",
         parent="delmont_msa", eff=-30, exp=400, annual=1_800 * K, total=3_600 * K,
         scope="Enterprise cyber risk assessment, zero-trust roadmap and SOC maturity review.", dev=[]),
    dict(key="delmont_amd1", title="Amendment No. 1 to MSA – Delmont Consulting", vendor=DEL,
         category="Consulting", type="Amendment", template="MSA",
         owner="Morgan Hayes (Finance Transformation)", parent="delmont_msa", eff=-45, exp=800,
         amend=[("term", {}), ("payment", {"payment_terms_days": 60})]),
    dict(key="delmont_wo1", title="Work Order 1 – Incident Response Retainer – Delmont Consulting",
         vendor=DEL, category="Security", type="Work Order", template="WO",
         owner="Taylor Reed (Security)", parent="delmont_sow2", eff=-25, exp=370, total=600 * K,
         scope="Prepaid 800-hour incident response and forensics retainer.", dev=[]),
    dict(key="delmont_nda", title="NDA – Delmont Consulting", vendor=DEL, category="Consulting",
         type="NDA", template="NDA", owner="Morgan Hayes (Finance Transformation)",
         parent="delmont_msa", eff=-718, exp=12, dev=[]),

    dict(key="taraka_msa", title="Master Services Agreement – Taraka Consultancy Services", vendor=TAR,
         category="IT Services", type="MSA", template="MSA", owner="Jordan Blake (IT Procurement)",
         eff=-250, exp=900, auto=False, dev=["governing_law:india", "payment:net30"]),
    dict(key="taraka_sow1", title="SOW 1 – Application Development and Maintenance (Offshore) – Taraka Consultancy Services",
         vendor=TAR, category="IT Services", type="SOW", template="SOW",
         owner="Jamie Cruz (Enterprise Apps)", parent="taraka_msa", eff=-240, exp=420,
         annual=6_000 * K, total=12_000 * K,
         scope="Offshore development and maintenance for loyalty, POS and supply-chain applications.",
         dev=[]),
    dict(key="taraka_sow2", title="SOW 2 – QA and Test Automation Centre of Excellence – Taraka Consultancy Services",
         vendor=TAR, category="IT Services", type="SOW", template="SOW",
         owner="Jamie Cruz (Enterprise Apps)", parent="taraka_msa", eff=-120, exp=410,
         annual=2_200 * K, total=4_400 * K,
         scope="Test automation framework and managed QA for release trains across 14 applications.",
         dev=[]),
    dict(key="taraka_wo1", title="Work Order 1 – Mainframe Modernization Assessment – Taraka Consultancy Services",
         vendor=TAR, category="IT Services", type="Work Order", template="WO",
         owner="Jamie Cruz (Enterprise Apps)", parent="taraka_sow1", eff=-45, exp=390, total=480 * K,
         scope="Assessment and migration roadmap for 62 COBOL batch applications.", dev=[]),
    dict(key="taraka_nda", title="NDA – Taraka Consultancy Services", vendor=TAR, category="IT Services",
         type="NDA", template="NDA", owner="Jordan Blake (IT Procurement)", parent="taraka_msa",
         eff=-260, exp=405, dev=[]),

    dict(key="nginova", title="Enterprise Subscription and Support Agreement – Nginova Systems",
         vendor=NGX, category="Software", type="SaaS", template="SaaS", owner="Sam Ortiz (Infrastructure)",
         eff=-200, exp=520, auto=False, annual=540 * K, total=1_620 * K, pd=False, dpa=False,
         dev=["sla:lower", "liability_cap:x2"]),
    dict(key="cirrus", title="SaaS Subscription Agreement – Cirrus CRM", vendor=CIR, category="SaaS",
         type="SaaS", template="SaaS", owner="Avery Patel (Customer Experience)", eff=-318, exp=47,
         auto=True, notice=30, annual=420 * K, total=420 * K, pd=True,
         subjects="customers and loyalty members", dpa=True, dev=["renewal:auto", "sla:lower"]),
    dict(key="ledgerline", title="SaaS Subscription Agreement – Ledgerline Finance Cloud", vendor=LED,
         category="SaaS", type="SaaS", template="SaaS", owner="Morgan Hayes (Finance Transformation)",
         eff=-290, exp=75, auto=True, notice=30, annual=650 * K, total=1_300 * K, pd=True,
         subjects="suppliers and employees", dpa=True,
         dev=["termination_for_convenience:none", "liability_cap:x2", "renewal:auto"]),
    dict(key="pulsehr", title="SaaS Subscription Agreement – PulseHR", vendor=PUL, category="SaaS",
         type="SaaS", template="SaaS", owner="Casey Lin (HR Technology)", eff=-15, exp=380, auto=True,
         notice=60, annual=340 * K, total=340 * K, pd=True, subjects="employees and job applicants",
         dpa=False, dev=["liability_cap:unlimited", "renewal:auto"]),
    dict(key="adspark", title="SaaS Subscription Agreement – AdSpark Analytics", vendor=ADS,
         category="Marketing", type="SaaS", template="SaaS", owner="Riley Chen (Digital Marketing)",
         eff=-344, exp=21, auto=True, notice=30, annual=220 * K, total=220 * K, pd=False, dpa=False,
         dev=["liability_cap:unlimited", "renewal:auto", "ip_ownership:supplier", "governing_law:singapore"]),
    dict(key="skyguard_nda", title="NDA – Skyguard Security", vendor=SKY, category="Security",
         type="NDA", template="NDA", owner="Taylor Reed (Security)", eff=-337, exp=28,
         dev=["governing_law:england"]),
    dict(key="cirrus_dpa", title="Data Processing Agreement – Cirrus CRM", vendor=CIR, category="SaaS",
         type="DPA", template="DPA", owner="Avery Patel (Customer Experience)", parent="cirrus",
         eff=-318, exp=800, dev=[]),
    dict(key="ledgerline_dpa", title="Data Processing Agreement – Ledgerline Finance Cloud", vendor=LED,
         category="SaaS", type="DPA", template="DPA", owner="Morgan Hayes (Finance Transformation)",
         parent="ledgerline", eff=-290, exp=800, dev=["breach_notification:h72"]),
]

# Vendor drafts. "missing" = template clause omitted from the draft.
DRAFTS: list[dict] = [
    dict(key="orbitline_msa", title="Draft MSA – Orbitline Cloud Hosting", vendor="Orbitline Cloud Hosting Inc",
         template="MSA", missing=[],
         dev=["liability_cap:unlimited", "indemnity:one_way", "payment:net15",
              "termination_for_convenience:none", "governing_law:england"]),
    dict(key="quanta_saas", title="Draft SaaS Agreement – Quanta Billing Cloud", vendor="Quanta Billing Technologies Inc",
         template="SaaS", missing=["data_return"],
         dev=["sla:weak", "security:slow", "data_protection:weak", "liability_cap:x05", "renewal:auto"]),
    dict(key="orbital_nda", title="Draft NDA – Orbital Security Labs", vendor="Orbital Security Labs Inc",
         template="NDA", missing=["non_solicit"], dev=["confidentiality:short", "governing_law:singapore"]),
    dict(key="vaultline_dpa", title="Draft DPA – Vaultline Data Services", vendor="Vaultline Data Services Inc",
         template="DPA", missing=[],
         dev=["subprocessors:general", "breach_notification:slow5", "cross_border:any", "audit_rights:none"]),
    dict(key="brightpath_sow", title="Draft SOW – Brightpath IT Staffing (clean control)",
         vendor="Brightpath IT Staffing Inc", template="SOW", missing=[], dev=[]),
]

# Fictional signatories. Customer signs for Arcadia; Legal signs NDAs and DPAs.
CUSTOMER_SIGNERS = {
    "default": ("Michael Brennan", "Chief Procurement Officer"),
    "legal": ("Dana Whitfield", "General Counsel"),
}
VENDOR_SIGNERS = {
    ACC: ("Laura Stephens", "Managing Director"),
    DEL: ("Richard Hale", "Partner"),
    TAR: ("Venkatesh Iyer", "VP Delivery"),
    NGX: ("Chris Dalton", "Chief Revenue Officer"),
    CIR: ("Emily Carter", "VP Sales"),
    LED: ("Farhan Qureshi", "Director"),
    PUL: ("Lakshmi Rao", "Founder and CEO"),
    ADS: ("Tanvi Joshi", "Partner"),
    SKY: ("Imran Sheikh", "Director"),
}
