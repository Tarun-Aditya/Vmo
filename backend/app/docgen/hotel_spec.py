"""Spec of the hotel corpus: a fictional hotel group ("Seabright Hotels & Resorts") and its vendor contracts, written from the owner-operator's side.
Same format as pilot_spec.py (each spec is the ground truth for one document; Claude writes the text, labels come from the spec). Extra key `prop` = the hotel the
contract is for; group-level master agreements have no property. Everything is fictional: no real hotel brand, vendor or contract wording is used.
Dates are offsets in days from the seed date."""
from __future__ import annotations

from app.docgen.pilot_spec import STYLES

CUSTOMER = "Seabright Hotels & Resorts Ltd"
CUSTOMER_DESC = "a hotel group that owns and operates six hotels; the 'Customer' is the group, services are delivered at individual hotels (the 'Properties')"
DOMAIN = "hotel-operations vendor relationship (hotel group buying services and supplies for its properties)"

H, M, L, A, S, O = ("Seabright Harbour Hotel", "Seabright Midtown Suites", "Seabright Lakeside Resort", "Seabright Airport Inn", "Seabright Old Town Boutique", "Seabright Summit Lodge")
OWN = ["Rhea Kapoor", "Daniel Moreau", "Imani Okoye", "Tomas Lindqvist"]

DOCS: list[dict] = [
    # ---- Crestline Laundry & Linen: group MSA, three property SOWs with DIFFERENT per-kg rates, an amendment, an NDA
    dict(key="crestline_msa", type="MSA", vendor="Crestline Laundry & Linen Services Ltd", cat="Laundry & Linen", owner=OWN[0], style="uk_numbered", fmt="pdf", eff=-540, term=36, pay=45, cap=1.0, tfc="60", law="England and Wales",
         auto=True, notice=90, sla=None, ins=5000000, warr=0, conf=3, pd=False, dpa=False, sign="both",
         extras=["Supplier guarantees linen turnaround within 48 hours of collection", "Supplier maintains a food-safe and infection-control laundering process and provides an annual compliance audit report"]),
    dict(key="crestline_sow_harbour", type="SOW", vendor="Crestline Laundry & Linen Services Ltd", cat="Laundry & Linen", owner=OWN[0], style="sow_form", fmt="docx", parent="crestline_msa", prop=H, eff=-500, term=24, annual=310_000, total=620_000, pay=45, cap="msa", law="England and Wales", auto=False, sign="both",
         extras=["Laundering charge is USD 1.42 per kilogram of linen, collected daily", "Supplier replaces linen lost or damaged beyond normal wear at its own cost"]),
    dict(key="crestline_sow_lakeside", type="SOW", vendor="Crestline Laundry & Linen Services Ltd", cat="Laundry & Linen", owner=OWN[0], style="sow_form", fmt="docx", parent="crestline_msa", prop=L, eff=-480, term=24, annual=265_000, total=530_000, pay=45, cap="msa", law="England and Wales", auto=False, sign="both",
         extras=["Laundering charge is USD 1.58 per kilogram of linen, collected five days a week", "Supplier replaces linen lost or damaged beyond normal wear at its own cost"]),
    dict(key="crestline_sow_airport", type="SOW", vendor="Crestline Laundry & Linen Services Ltd", cat="Laundry & Linen", owner=OWN[1], style="sow_form", fmt="pdf", parent="crestline_msa", prop=A, eff=-300, term=18, annual=198_000, total=297_000, pay=45, cap="msa", law="England and Wales", auto=False, sign="both",
         extras=["Laundering charge is USD 1.71 per kilogram of linen, collected daily including weekends", "Supplier replaces linen lost or damaged beyond normal wear at its own cost"]),
    dict(key="crestline_amd1", type="Amendment", vendor="Crestline Laundry & Linen Services Ltd", cat="Laundry & Linen", owner=OWN[0], style="short_form", fmt="docx", amends="crestline_msa", eff=-150, ov=dict(payment_terms_days=30, expiry_term_months=48), sign="both"),
    dict(key="crestline_nda", type="NDA", vendor="Crestline Laundry & Linen Services Ltd", cat="Laundry & Linen", owner=OWN[0], style="short_form", fmt="md", eff=-560, term=36, law="England and Wales", conf=3, sign="both"),
    # ---- Brightstar Security Services: no termination for convenience
    dict(key="brightstar_msa", type="MSA", vendor="Brightstar Security Services Inc", cat="Security", owner=OWN[1], style="us_articles", fmt="docx", eff=-400, term=36, pay=30, cap=1.0, tfc="no", law="New York", auto=True, notice=60, ins=10_000_000, warr=0, conf=3, pd=False, dpa=False, sign="both",
         extras=["Supplier's guards hold current licences and complete background checks; Supplier complies with applicable minimum-wage and working-time law", "Supplier responds to an alarm activation at a Property within 15 minutes"]),
    dict(key="brightstar_sow_harbour", type="SOW", vendor="Brightstar Security Services Inc", cat="Security", owner=OWN[1], style="sow_form", fmt="pdf", parent="brightstar_msa", prop=H, eff=-390, term=24, annual=420_000, total=840_000, pay=30, cap="msa", law="New York", auto=False, sign="both"),
    dict(key="brightstar_sow_midtown", type="SOW", vendor="Brightstar Security Services Inc", cat="Security", owner=OWN[1], style="sow_form", fmt="docx", parent="brightstar_msa", prop=M, eff=-200, term=12, annual=240_000, total=240_000, pay=30, cap="msa", law="New York", auto=False, sign="both"),
    # ---- Halcyon Elevator & Lift Maintenance: repair response times, auto-renew, notice close
    dict(key="halcyon_msa", type="MSA", vendor="Halcyon Elevator & Lift Maintenance Ltd", cat="Lifts & Engineering", owner=OWN[2], style="schedule_heavy", fmt="pdf", eff=-700, term=36, pay=30, cap=2.0, tfc="90", law="England and Wales", auto=True, notice=120,
         sla=None, ins=5_000_000, warr=90, conf=2, pd=False, dpa=False, sign="both", annual=180_000, total=540_000,
         extras=["Supplier attends a passenger entrapment within 1 hour and any other lift fault within 4 hours", "Supplier performs statutory thorough examinations of every lift and delivers the inspection certificates to the Customer"]),
    dict(key="halcyon_sow_midtown", type="SOW", vendor="Halcyon Elevator & Lift Maintenance Ltd", cat="Lifts & Engineering", owner=OWN[2], style="sow_form", fmt="docx", parent="halcyon_msa", prop=M, eff=-680, term=36, annual=96_000, total=288_000, pay=30, cap="msa", law="England and Wales", auto=False, sign="both"),
    dict(key="halcyon_sow_summit", type="SOW", vendor="Halcyon Elevator & Lift Maintenance Ltd", cat="Lifts & Engineering", owner=OWN[2], style="sow_form", fmt="docx", parent="halcyon_msa", prop=O, eff=-650, term=36, annual=84_000, total=252_000, pay=30, cap="msa", law="England and Wales", auto=False, sign="both"),
    # ---- Verdant Pest Control: short form, one property
    dict(key="verdant_msa", type="MSA", vendor="Verdant Pest Control Ltd", cat="Pest Control", owner=OWN[2], style="plain", fmt="docx", prop=L, eff=-250, term=12, annual=36_000, total=36_000, pay=30, cap=1.0, tfc="30", law="England and Wales", auto=True, notice=30, ins=2_000_000, warr=0, conf=2, pd=False, dpa=False, sign="both",
         extras=["Supplier visits the Property monthly and within 24 hours of a guest-reported pest sighting", "Supplier's treatments comply with food-safety standards for kitchens and food stores"]),
    # ---- Northgate Facilities & HVAC
    dict(key="northgate_msa", type="MSA", vendor="Northgate Facilities & HVAC Inc", cat="Facilities & HVAC", owner=OWN[3], style="us_sections", fmt="docx", eff=-380, term=36, pay=45, cap=1.0, tfc="30", law="Illinois", auto=False, ins=5_000_000, warr=365, conf=3, pd=False, dpa=False, sign="both",
         extras=["Supplier restores heating or cooling in guest rooms within 4 hours of a fault report at any Property", "Supplier delivers a monthly planned-maintenance report per Property"]),
    dict(key="northgate_sow_harbour", type="SOW", vendor="Northgate Facilities & HVAC Inc", cat="Facilities & HVAC", owner=OWN[3], style="sow_form", fmt="pdf", parent="northgate_msa", prop=H, eff=-370, term=24, annual=540_000, total=1_080_000, pay=45, cap="msa", law="Illinois", auto=False, sign="both",
         ms=[("Planned-maintenance schedule agreed", -350), ("Chiller replacement complete", 40)]),
    # ---- Evergreen Waste & Recycling: auto-renewal, notice already passed
    dict(key="evergreen_msa", type="MSA", vendor="Evergreen Waste & Recycling Ltd", cat="Waste & Sustainability", owner=OWN[3], style="short_form", fmt="docx", prop=S, eff=-335, term=12, annual=54_000, total=54_000, pay=30, cap=1.0, tfc="no", law="England and Wales", auto=True, notice=60, ins=2_000_000, warr=0, conf=1, pd=False, dpa=False, sign="both"),
    # ---- Hearth & Table Foods: F&B supplier, seasonal pricing, unlimited liability
    dict(key="hearth_msa", type="MSA", vendor="Hearth & Table Foods Inc", cat="Food & Beverage Supply", owner=OWN[1], style="vendor_paper", fmt="pdf", eff=-310, term=24, annual=1_250_000, total=2_500_000, pay=15, cap="unlimited", tfc="no", law="California", auto=True, notice=45, ins=5_000_000, warr=0, conf=2, pd=False, dpa=False, sign="both",
         extras=["Supplier may adjust prices for seasonal produce once per calendar quarter on 14 days' notice", "Supplier maintains food-safety certification (HACCP) and notifies the Customer of any product recall within 24 hours"]),
    # ---- Staffwell Hospitality Staffing: housekeeping agency staff, one SOW unsigned
    dict(key="staffwell_msa", type="MSA", vendor="Staffwell Hospitality Staffing Ltd", cat="Staffing", owner=OWN[0], style="uk_numbered", fmt="docx", eff=-420, term=24, pay=14, cap=1.0, tfc="30", law="England and Wales", auto=True, notice=60, ins=5_000_000, warr=0, conf=2, pd=True, dpa=False, sign="both",
         extras=["Supplier pays all agency workers at least the applicable minimum wage and complies with working-time rules", "Supplier supplies replacement housekeeping staff within 4 hours when a worker is absent"]),
    dict(key="staffwell_sow_airport", type="SOW", vendor="Staffwell Hospitality Staffing Ltd", cat="Staffing", owner=OWN[1], style="sow_form", fmt="docx", parent="staffwell_msa", prop=A, eff=-400, term=24, annual=610_000, total=1_220_000, pay=14, cap="msa", law="England and Wales", auto=False, sign="both"),
    dict(key="staffwell_sow_harbour", type="SOW", vendor="Staffwell Hospitality Staffing Ltd", cat="Staffing", owner=OWN[0], style="short_form", fmt="docx", parent="staffwell_msa", prop=H, eff=-25, term=12, annual=450_000, total=450_000, pay=14, cap="msa", law="England and Wales", auto=False, sign="supplier"),
    # ---- Stayflow Property Systems: PMS software (guest data) with a DPA; NDA
    dict(key="stayflow_saas", type="SaaS", vendor="Stayflow Property Systems Inc", cat="Hotel Technology", owner=OWN[2], style="us_sections", fmt="pdf", eff=-260, term=36, annual=348_000, total=1_044_000, pay=30, cap=2.0, tfc="no", law="Delaware", auto=True, notice=90, sla=99.9, inc=24, warr=30, conf=3, pd=True, dpa=True, sign="both",
         extras=["Supplier processes payment-card data only through PCI DSS compliant systems and provides an annual attestation of compliance", "Supplier keeps the property management system available 99.9% each month"]),
    dict(key="stayflow_dpa", type="DPA", vendor="Stayflow Property Systems Inc", cat="Hotel Technology", owner=OWN[2], style="uk_numbered", fmt="docx", parent="stayflow_saas", eff=-255, term=36, law="Delaware", pd=True, sign="both"),
    dict(key="stayflow_nda", type="NDA", vendor="Stayflow Property Systems Inc", cat="Hotel Technology", owner=OWN[2], style="plain", fmt="md", eff=-290, term=24, law="Delaware", conf=3, sign="both"),
    # ---- BookWave Distribution: online booking channel, guest personal data, NO DPA (planted risk)
    dict(key="bookwave_saas", type="SaaS", vendor="BookWave Distribution Inc", cat="Distribution & Booking", owner=OWN[3], style="vendor_paper", fmt="pdf", eff=-340, term=12, annual=420_000, total=420_000, pay=30, cap=0.5, tfc="no", law="Nevada", auto=True, notice=60, sla=99.0, inc=96, warr=0, conf=2, pd=True, dpa=False, sign="both",
         extras=["The Customer pays BookWave a commission of 15 percent of the room revenue of each booking made through the BookWave channel", "BookWave receives guest names, contact details and payment references for each booking"]),
    # ---- PayGuard Payments: payment processing with DPA
    dict(key="payguard_saas", type="SaaS", vendor="PayGuard Payments Pte Ltd", cat="Hotel Technology", owner=OWN[2], style="schedule_heavy", fmt="docx", eff=-180, term=36, annual=190_000, total=570_000, pay=30, cap=2.0, tfc="90", law="Singapore", auto=False, sla=99.95, inc=24, warr=30, conf=3, pd=True, dpa=True, sign="both",
         extras=["Supplier maintains PCI DSS compliance and provides its annual attestation of compliance"]),
    dict(key="payguard_dpa", type="DPA", vendor="PayGuard Payments Pte Ltd", cat="Hotel Technology", owner=OWN[2], style="us_sections", fmt="pdf", parent="payguard_saas", eff=-175, term=36, law="Singapore", pd=True, sign="both"),
    # ---- Lumen Energy Supply: fixed-price energy contract expiring soon
    dict(key="lumen_msa", type="MSA", vendor="Lumen Energy Supply Ltd", cat="Energy & Utilities", owner=OWN[3], style="schedule_heavy", fmt="pdf", eff=-1030, term=36, annual=2_100_000, total=6_300_000, pay=21, cap=1.0, tfc="no", law="England and Wales", auto=False, ins=None, warr=0, conf=1, pd=False, dpa=False, sign="both",
         extras=["Electricity and gas are supplied to all six Properties at a fixed unit price for the whole term", "The fixed price ends on expiry and the Customer must arrange a new supply before then"]),
    # ---- Vendor drafts for redline (planted deviations) + one clean control
    dict(key="draft_crestline_renewal", type="SOW", status="draft", vendor="Crestline Laundry & Linen Services Ltd", cat="Laundry & Linen", owner=OWN[0], style="sow_form", fmt="docx", prop=H, eff=20, term=24, annual=348_000, total=696_000, pay=10, cap=0.25, tfc="no", law="Delaware",
         auto=True, notice=180, sign="none", extras=["Laundering charge rises to USD 1.62 per kilogram of linen"], dev=["payment_terms", "liability_cap", "termination_for_convenience", "renewal"]),
    dict(key="draft_halcyon_renewal", type="MSA", status="draft", vendor="Halcyon Elevator & Lift Maintenance Ltd", cat="Lifts & Engineering", owner=OWN[2], style="us_articles", fmt="docx", eff=25, term=36, pay=10, cap="unlimited", tfc="no", law="England and Wales",
         auto=True, notice=180, ins=1_000_000, warr=0, conf=2, pd=False, dpa=False, sign="none", extras=["Supplier attends any lift fault within 24 hours"], dev=["payment_terms", "liability_cap", "termination_for_convenience", "renewal", "insurance"]),
    dict(key="draft_pristine_msa", type="MSA", status="draft", vendor="Pristine Spa & Amenity Supplies Inc", cat="Guest Amenities", owner=OWN[1], style="vendor_paper", fmt="docx", eff=15, term=24, annual=330_000, total=660_000, pay=15, cap=0.5, tfc="no", law="Florida",
         auto=True, notice=90, ins=1_000_000, warr=0, conf=1, pd=False, dpa=False, sign="none", dev=["payment_terms", "liability_cap", "termination_for_convenience"]),
    dict(key="draft_bookwave_renewal", type="SaaS", status="draft", vendor="BookWave Distribution Inc", cat="Distribution & Booking", owner=OWN[3], style="vendor_paper", fmt="pdf", eff=30, term=24, annual=480_000, total=960_000, pay=15, cap=0.25, tfc="no", law="Nevada",
         auto=True, notice=180, sla=98.0, inc=120, warr=0, conf=2, pd=True, dpa=False, sign="none", extras=["The commission rises to 18 percent of room revenue"], dev=["payment_terms", "liability_cap", "renewal", "sla", "data_protection"]),
    dict(key="draft_nda_clean", type="NDA", status="draft", vendor="Marlowe Hospitality Consulting LLP", cat="Consulting", owner=OWN[0], style="us_sections", fmt="docx", eff=10, term=24, law="New York", conf=3, sign="none", dev=[]),
]
