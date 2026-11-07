"""Spec of the pilot corpus: ~34 realistic (fictional) IT-services contracts. Each spec is the ground truth for one document:
Claude writes the contract text from it in a given drafting style (scripts/build_pilot_corpus.py), the labels are computed from the spec, never from the text.
Dates are offsets in days from the seed date and are filled in at seed time, so the dashboard always looks current."""
from __future__ import annotations

CUSTOMER = "Arcadia Retail Inc."

STYLES = {
    "us_articles": "US enterprise paper: ARTICLE headings (ARTICLE 1 – DEFINITIONS ...), numbered sections 1.1, 1.2; defined terms in bold quotes; formal; 'Customer' and 'Supplier' defined by short names (e.g. Arcadia / the vendor's short name).",
    "uk_numbered": "English-law style: numbered clauses 1., 1.1, 1.1.1; 'Schedule 1 – Services', 'Schedule 2 – Charges' near the end; spelling such as 'licence', 'programme'; 'the Client' and 'the Supplier'.",
    "plain": "Plain-language short form: friendly headings ('What you are buying', 'How we charge', 'If something goes wrong'), short paragraphs, 'we/you' voice, still legally complete.",
    "schedule_heavy": "Master terms followed by Schedules and Order Forms; key commercial terms (fees, term, SLA targets) live in a table in the Order Form or Schedule; terms refer to the Order Form.",
    "short_form": "Two- to three-page short-form agreement; terse numbered paragraphs; minimal headings; fees and term in the opening paragraphs.",
    "vendor_paper": "Vendor-friendly paper, assertive: broad disclaimers, vendor-favourable defaults, long exclusions; sections headed in capitals.",
    "us_sections": "US style with 'Section 1. Definitions' ... 'Section 14. Miscellaneous'; recitals ('WHEREAS') at the start; signature block with By/Name/Title/Date lines.",
    "sow_form": "Statement of Work form: header block (Project, Parent Agreement, Period, Fees) then sections: Background, Scope, Deliverables and Milestones (table), Roles, Assumptions, Fees and Invoicing, Acceptance.",
}

# fields: eff (days from seed), term (months), annual, total, pay (days), cap (float multiple | 'unlimited' | 'msa' | None), tfc ('N' days notice | 'no' | None),
# law, auto, notice, sla, inc (hours), ins (USD), warr (days), conf (years), pd (processes personal data), dpa (has DPA), sign ('both'|'supplier'|'customer'|'none'),
# ms (milestones: [(description, offset days)]), extras (other duties the text must state), parent (key), amends (key) + ov (overridden fields), fmt, style, owner, cat, vendor
DOCS: list[dict] = [
    # ---- Helix Digital Consulting: global systems integrator (biggest vendor)
    dict(key="helix_msa", type="MSA", vendor="Helix Digital Consulting Inc", cat="IT Services", owner="Jordan Blake", style="us_articles", fmt="docx", eff=-420, term=36, pay=45, cap=1.0, tfc="30", law="New York", auto=False, ins=5_000_000, warr=90, conf=3, pd=True, dpa=False, sign="both",
         extras=["Supplier delivers a written monthly service report by the 5th business day", "Supplier maintains an information security programme and provides an annual SOC 2 Type II report"]),
    dict(key="helix_sow1", type="SOW", vendor="Helix Digital Consulting Inc", cat="IT Services", owner="Jordan Blake", style="sow_form", fmt="pdf", parent="helix_msa", eff=-380, term=18, annual=6_400_000, total=9_600_000, pay=45, cap="msa", law="New York", auto=False, sign="both",
         ms=[("Mobilisation and delivery plan accepted", -350), ("Design complete and signed off", -250), ("Wave 1 go-live", -60), ("Wave 2 go-live and handover", 90)],
         extras=["Supplier holds a weekly steering committee and monthly governance review"]),
    dict(key="helix_sow2", type="SOW", vendor="Helix Digital Consulting Inc", cat="IT Services", owner="Priya Nair", style="sow_form", fmt="docx", parent="helix_msa", eff=-200, term=24, annual=3_100_000, total=6_200_000, pay=45, cap="msa", law="New York", auto=False, sign="both",
         ms=[("Data platform architecture approved", -170), ("Core pipelines in production", -40), ("Analytics handover and knowledge transfer", 200)]),
    dict(key="helix_wo1", type="Work Order", vendor="Helix Digital Consulting Inc", cat="IT Services", owner="Priya Nair", style="short_form", fmt="md", parent="helix_sow1", eff=-45, term=6, total=420_000, pay=45, cap="msa", law="New York", sign="supplier",
         ms=[("Interface specification delivered", 20), ("Cutover rehearsal complete", 60)]),
    dict(key="helix_amd1", type="Amendment", vendor="Helix Digital Consulting Inc", cat="IT Services", owner="Jordan Blake", style="short_form", fmt="docx", amends="helix_msa", eff=-120, ov=dict(payment_terms_days=60, expiry_term_months=48), sign="both"),
    # ---- Tatva Infosystems: offshore ADM
    dict(key="tatva_msa", type="MSA", vendor="Tatva Infosystems Ltd", cat="IT Services", owner="Sam Ortiz", style="uk_numbered", fmt="pdf", eff=-300, term=36, pay=30, cap=2.0, tfc="60", law="England and Wales", auto=True, notice=90, ins=2_000_000, warr=60, conf=5, pd=True, dpa=True, sign="both",
         extras=["Supplier delivers monthly SLA and productivity reports", "Supplier gives 15 days' notice before replacing key personnel"]),
    dict(key="tatva_sow1", type="SOW", vendor="Tatva Infosystems Ltd", cat="IT Services", owner="Sam Ortiz", style="sow_form", fmt="docx", parent="tatva_msa", eff=-290, term=24, annual=4_200_000, total=8_400_000, pay=30, cap="msa", law="England and Wales", sign="both", sla=99.0,
         ms=[("Knowledge transition complete", -240), ("Steady-state operations begin", -200), ("First annual benchmarking review", 75)]),
    dict(key="tatva_wo1", type="Work Order", vendor="Tatva Infosystems Ltd", cat="IT Services", owner="Sam Ortiz", style="short_form", fmt="md", parent="tatva_sow1", eff=-60, term=5, total=260_000, pay=30, cap="msa", law="England and Wales", sign="both", ms=[("Mainframe assessment report", 35)]),
    # ---- Meridian Cloud Services: hosting, SLA + service credits table
    dict(key="meridian_msa", type="MSA", vendor="Meridian Cloud Services LLC", cat="Cloud", owner="Sam Ortiz", style="schedule_heavy", fmt="pdf", eff=-500, term=48, pay=45, cap=1.0, tfc="90", law="Delaware", auto=True, notice=120, sla=99.95, inc=24, ins=5_000_000, warr=90, conf=3, pd=True, dpa=True, sign="both",
         annual=2_400_000, total=9_600_000, extras=["Supplier delivers a monthly availability report and a quarterly business review", "Supplier provides service credits of 5%, 10% and 25% of the monthly fee for availability misses"]),
    dict(key="meridian_dpa", type="DPA", vendor="Meridian Cloud Services LLC", cat="Cloud", owner="Sam Ortiz", style="us_sections", fmt="docx", parent="meridian_msa", eff=-495, term=48, law="Delaware", pd=True, sign="both", extras=["Supplier notifies a personal data breach within 48 hours", "Supplier lists sub-processors and gives 30 days' notice of changes"]),
    # ---- Zenith Software: SaaS, plain language
    dict(key="zenith_saas", type="SaaS", vendor="Zenith Software Ltd", cat="SaaS", owner="Jordan Blake", style="plain", fmt="docx", eff=-150, term=12, annual=360_000, total=360_000, pay=30, cap=1.0, tfc="no", law="California", auto=True, notice=60, sla=99.9, inc=48, ins=2_000_000, warr=30, conf=3, pd=True, dpa=False, sign="both",
         extras=["Supplier reports availability each month"]),
    # ---- Bluepeak Analytics: SaaS with DPA
    dict(key="bluepeak_saas", type="SaaS", vendor="Bluepeak Analytics Inc", cat="SaaS", owner="Priya Nair", style="us_sections", fmt="pdf", eff=-250, term=24, annual=540_000, total=1_080_000, pay=45, cap=2.0, tfc="30", law="New York", auto=True, notice=90, sla=99.5, inc=72, ins=3_000_000, warr=60, conf=3, pd=True, dpa=True, sign="both"),
    dict(key="bluepeak_dpa", type="DPA", vendor="Bluepeak Analytics Inc", cat="SaaS", owner="Priya Nair", style="short_form", fmt="md", parent="bluepeak_saas", eff=-245, term=24, law="New York", pd=True, sign="both"),
    # ---- Kestrel Marketing Cloud: SaaS auto-renewal, notice already passed, unlimited liability
    dict(key="kestrel_saas", type="SaaS", vendor="Kestrel Marketing Cloud Inc", cat="Marketing", owner="Lena Fischer", style="vendor_paper", fmt="pdf", eff=-335, term=12, annual=210_000, total=210_000, pay=60, cap="unlimited", tfc="no", law="Delaware", auto=True, notice=45, sla=99.0, inc=96, warr=30, conf=2, pd=True, dpa=False, sign="both"),
    # ---- CoreLedger Payments: SaaS + cross-border
    dict(key="coreledger_saas", type="SaaS", vendor="CoreLedger Payments Pte Ltd", cat="SaaS", owner="Lena Fischer", style="schedule_heavy", fmt="docx", eff=-100, term=36, annual=780_000, total=2_340_000, pay=30, cap=1.0, tfc="60", law="Singapore", auto=False, sla=99.9, inc=24, ins=5_000_000, warr=90, conf=5, pd=True, dpa=True, sign="both",
         extras=["Supplier delivers an annual penetration test summary", "Supplier notifies a personal data breach within 24 hours"]),
    dict(key="coreledger_dpa", type="DPA", vendor="CoreLedger Payments Pte Ltd", cat="SaaS", owner="Lena Fischer", style="uk_numbered", fmt="pdf", parent="coreledger_saas", eff=-95, term=36, law="Singapore", pd=True, sign="both"),
    # ---- Orion Cybersecurity Partners
    dict(key="orion_msa", type="MSA", vendor="Orion Cybersecurity Partners LLP", cat="Security", owner="Sam Ortiz", style="uk_numbered", fmt="docx", eff=-260, term=36, pay=30, cap="unlimited", tfc="no", law="England and Wales", auto=False, ins=10_000_000, warr=60, conf=7, pd=False, dpa=False, sign="both"),
    dict(key="orion_sow1", type="SOW", vendor="Orion Cybersecurity Partners LLP", cat="Security", owner="Sam Ortiz", style="sow_form", fmt="docx", parent="orion_msa", eff=-120, term=12, annual=950_000, total=950_000, pay=30, cap="msa", law="England and Wales", sign="both",
         ms=[("Baseline assessment report", -90), ("Remediation roadmap delivered", -20), ("Retest and closure report", 150)], extras=["Supplier gives 24 hours' notice of any critical finding"]),
    dict(key="orion_nda", type="NDA", vendor="Orion Cybersecurity Partners LLP", cat="Security", owner="Sam Ortiz", style="short_form", fmt="md", eff=-280, term=36, law="England and Wales", conf=7, sign="both"),
    # ---- Vantage Telecom Services: network, SLA table
    dict(key="vantage_msa", type="MSA", vendor="Vantage Telecom Services Inc", cat="Telecom", owner="Jordan Blake", style="schedule_heavy", fmt="pdf", eff=-700, term=60, pay=60, cap=1.0, tfc="no", law="Texas", auto=True, notice=180, sla=99.99, inc=4, ins=5_000_000, warr=0, conf=3, pd=False, dpa=False, sign="both", annual=1_320_000, total=6_600_000,
         extras=["Supplier provides monthly SLA reports with service credits"]),
    # ---- Quill Staffing: unsigned
    dict(key="quill_sow", type="SOW", vendor="Quill Staffing Group Ltd", cat="Staffing", owner="Lena Fischer", style="short_form", fmt="docx", eff=-30, term=12, annual=780_000, total=780_000, pay=30, cap=1.0, tfc="14", law="New York", auto=False, sign="supplier"),
    dict(key="quill_nda", type="NDA", vendor="Quill Staffing Group Ltd", cat="Staffing", owner="Lena Fischer", style="plain", fmt="md", eff=-40, term=24, law="New York", conf=2, sign="both"),
    # ---- Ironbridge Data Centers: colocation, expiring soon
    dict(key="ironbridge_msa", type="MSA", vendor="Ironbridge Data Centers Inc", cat="Cloud", owner="Sam Ortiz", style="us_articles", fmt="pdf", eff=-1010, term=36, pay=45, cap=1.0, tfc="no", law="Virginia", auto=False, sla=99.99, inc=12, ins=5_000_000, warr=0, conf=3, pd=False, dpa=False, sign="both", annual=1_800_000, total=5_400_000),
    # ---- Atlas Facilities Tech: expiring in 40 days, auto-renew
    dict(key="atlas_saas", type="SaaS", vendor="Atlas Facilities Tech Inc", cat="SaaS", owner="Priya Nair", style="short_form", fmt="docx", eff=-325, term=12, annual=96_000, total=96_000, pay=30, cap=1.0, tfc="30", law="Illinois", auto=True, notice=30, sla=99.5, inc=48, warr=30, conf=2, pd=False, dpa=False, sign="both"),
    # ---- Sable Legal Tech NDA (shorter confidentiality)
    dict(key="sable_nda", type="NDA", vendor="Sable Legal Tech Inc", cat="Legal", owner="Lena Fischer", style="plain", fmt="docx", eff=-200, term=24, law="New York", conf=1, sign="both"),
    # ---- Lumina Learning: SaaS processes personal data WITHOUT a DPA
    dict(key="lumina_saas", type="SaaS", vendor="Lumina Learning Systems Inc", cat="SaaS", owner="Jordan Blake", style="vendor_paper", fmt="pdf", eff=-60, term=24, annual=275_000, total=550_000, pay=30, cap=0.5, tfc="no", law="Massachusetts", auto=True, notice=60, sla=99.0, inc=96, warr=30, conf=2, pd=True, dpa=False, sign="both"),
    # ---- Granite Network Integrators: no-contract-style vendor, only draft MSA (spend without contract)
    dict(key="granite_draft_msa", type="MSA", status="draft", vendor="Granite Network Integrators Inc", cat="IT Services", owner="Sam Ortiz", style="vendor_paper", fmt="docx", eff=15, term=24, pay=15, cap="unlimited", tfc="no", law="Georgia", auto=True, notice=30, ins=500_000, warr=0, conf=1, pd=True, dpa=False, sign="none",
         dev=["payment_terms", "liability_cap", "termination_for_convenience", "renewal", "governing_law"]),
    # ---- Drafts for redline (vendor paper in different styles)
    dict(key="draft_saas_nimbus", type="SaaS", status="draft", vendor="Nimbus Workflow Inc", cat="SaaS", owner="Priya Nair", style="vendor_paper", fmt="docx", eff=20, term=36, annual=480_000, total=1_440_000, pay=20, cap=0.25, tfc="no", law="Delaware", auto=True, notice=120, sla=97.0, inc=168, warr=0, conf=1, pd=True, dpa=False, sign="none",
         dev=["payment_terms", "liability_cap", "termination_for_convenience", "renewal", "sla", "data_protection", "warranties"]),
    dict(key="draft_sow_cobalt", type="SOW", status="draft", vendor="Cobalt Applications Group", cat="IT Services", owner="Jordan Blake", style="sow_form", fmt="docx", eff=25, term=12, annual=1_100_000, total=1_100_000, pay=15, cap="unlimited", law="Florida", sign="none",
         dev=["payment_terms", "liability_cap", "ip_ownership"]),
    dict(key="draft_nda_pinecrest", type="NDA", status="draft", vendor="Pinecrest Advisory LLP", cat="Consulting", owner="Lena Fischer", style="us_sections", fmt="pdf", eff=10, term=60, law="Ohio", conf=10, sign="none", dev=["confidentiality", "governing_law", "non_solicit"]),
    dict(key="draft_msa_vertex", type="MSA", status="draft", vendor="Vertex Managed Services Inc", cat="IT Services", owner="Sam Ortiz", style="us_articles", fmt="docx", eff=30, term=36, pay=45, cap=1.0, tfc="30", law="New York", auto=False, ins=5_000_000, warr=90, conf=3, pd=True, dpa=True, sign="none", dev=[]),
    dict(key="helix_wo2", type="Work Order", vendor="Helix Digital Consulting Inc", cat="IT Services", owner="Priya Nair", style="short_form", fmt="docx", parent="helix_sow2", eff=-15, term=4, total=185_000, pay=45, cap="msa", law="New York", sign="both", ms=[("Test automation framework delivered", 50)]),
    dict(key="tatva_sow2", type="SOW", vendor="Tatva Infosystems Ltd", cat="IT Services", owner="Sam Ortiz", style="sow_form", fmt="pdf", parent="tatva_msa", eff=-90, term=12, annual=1_850_000, total=1_850_000, pay=30, cap="msa", law="England and Wales", sign="both", sla=99.5,
         ms=[("QA centre of excellence established", -50), ("Automation coverage reaches 60 percent", 40)]),
    dict(key="meridian_sow1", type="SOW", vendor="Meridian Cloud Services LLC", cat="Cloud", owner="Sam Ortiz", style="sow_form", fmt="docx", parent="meridian_msa", eff=-110, term=9, annual=900_000, total=675_000, pay=45, cap="msa", law="Delaware", sign="both",
         ms=[("Landing zone ready", -80), ("Workload migration wave 1", -10), ("Workload migration wave 2", 70)]),
    dict(key="vantage_sow1", type="SOW", vendor="Vantage Telecom Services Inc", cat="Telecom", owner="Jordan Blake", style="sow_form", fmt="pdf", parent="vantage_msa", eff=-70, term=10, annual=0, total=540_000, pay=60, cap="msa", law="Texas", sign="supplier", ms=[("Site survey complete", -40), ("Circuit installation complete", 55)]),
    dict(key="atlas_nda", type="NDA", vendor="Atlas Facilities Tech Inc", cat="SaaS", owner="Priya Nair", style="short_form", fmt="md", eff=-340, term=24, law="Illinois", conf=3, sign="both"),
]
