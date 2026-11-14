"""Hospitality configuration pack: the key clauses, values and checklist rules a hotel group looks for in vendor contracts.
Loaded with `python -m app.seed --hotel` (or `hotel_pack.ensure(session)`); every row is ordinary Admin configuration (editable, deletable, not built in)."""
from __future__ import annotations

from sqlalchemy import text

from app import kcc
from app.docgen.hotel_house import HOUSE

CAT = "Hospitality"


def _k(key, name, desc, keywords, aliases, std, sev, applies, matrix=True):
    return dict(key=key, name=name, description=desc, category=CAT, keywords=keywords, heading_aliases=aliases, standard_text=std, playbook_position=desc, fallback_text=None,
                severity_if_missing=sev, applies_to=applies, in_matrix=matrix, enabled=True, sort_order=900, builtin=False)


CLAUSES = [
    _k("food_safety", "Food safety", "Supplier keeps food-safety certification (HACCP) and handles recalls promptly", ["haccp", "food[- ]safety", "product recall"], ["Food Safety", "Food Hygiene"],
       "The Supplier shall maintain food-safety certification (HACCP) throughout the term and shall notify the Customer of any product recall within 24 hours.", "high", ["MSA", "SOW"]),
    _k("guest_injury_indemnity", "Guest injury indemnity", "Supplier indemnifies the hotel for guest or staff injury caused by its work", [r"guest[s]?\b[^.]{0,80}\b(?:injur|harm|death)", r"injur[^.]{0,80}\bguest", "bodily injury"], ["Guest Injury", "Personal Injury"],
       "The Supplier shall indemnify the Customer against claims by guests or staff for injury, illness or death caused by the Supplier's acts, omissions or equipment.", "high", ["MSA"]),
    _k("labour_compliance", "Labour and wage compliance", "Supplier pays at least the minimum wage and follows working-time law for staff at the property", ["minimum[- ]wage", "working[- ]time", "modern slavery", "labour (?:law|standards)"], ["Labour Compliance", "Employment Compliance"],
       "The Supplier shall pay all personnel at least the applicable minimum wage, comply with working-time rules and shall not use forced or underage labour.", "high", ["MSA", "SOW"]),
    _k("property_sale_termination", "Termination on sale of property", "The hotel can end the services if the property is sold or the operator changes", [r"sale of (?:the|a|any) (?:property|hotel)", "change of (?:ownership|control)", r"disposal of the (?:property|hotel)"], ["Sale of Property", "Change of Ownership"],
       "The Customer may terminate the services at a Property on 30 days' notice, without penalty, if the Property is sold or ceases to be operated by the Customer.", "medium", ["MSA", "SOW"]),
    _k("brand_standards", "Brand and operating standards", "Supplier meets the hotel brand's operating and quality standards", ["brand standards?", "operating standards?", "quality standards?"], ["Brand Standards", "Operating Standards"],
       "The Supplier shall perform the services to the brand and operating standards notified by the Customer from time to time.", "medium", ["MSA", "SOW"]),
    _k("seasonal_pricing", "Seasonal pricing", "Price changes by season or quarter are capped and notified", ["seasonal", "price adjustment", "price review"], ["Seasonal Pricing", "Price Adjustment"],
       "Prices may change only once per calendar quarter, by no more than 5 percent, on 30 days' written notice.", "medium", ["MSA", "SaaS"]),
    _k("payment_card_data", "Payment-card data security", "PCI DSS compliance where the supplier handles card data", ["pci[- ]dss", "payment[- ]card"], ["Payment Card Security", "PCI DSS"],
       "The Supplier shall comply with PCI DSS wherever it stores, processes or transmits payment-card data and shall provide its annual attestation of compliance.", "critical", ["SaaS", "MSA"]),
    _k("service_response", "Response and turnaround times", "Time to respond to faults and to turn around work", [r"within \d+ hours?", "response time", "turnaround"], ["Response Times", "Service Levels", "Turnaround"],
       "The Supplier shall respond to a fault report within 4 hours and complete urgent repairs within 24 hours.", "medium", ["MSA", "SOW"]),
    _k("inspection_certificates", "Inspection and compliance certificates", "Supplier delivers statutory inspection and compliance certificates", ["inspection certificate", "statutory (?:thorough )?examination", r"certificate[s]? of (?:compliance|inspection)", "attestation of compliance"], ["Certificates", "Statutory Inspections"],
       "The Supplier shall deliver copies of every statutory inspection and compliance certificate to the Customer when issued and before the previous one expires.", "medium", ["MSA", "SOW"]),
    _k("distribution_commission", "Distribution commission", "Commission payable on bookings through a distribution channel", [r"commission of \d", "commission rate", r"commission[^.]{0,40}room revenue"], ["Commission", "Distribution Fees"],
       "The commission payable on each booking shall not exceed 15 percent of the room revenue of that booking.", "high", ["SaaS"], matrix=False),
]


for _c in CLAUSES:            # one wording for the template and the clause library
    if _c["key"] in HOUSE:
        _c["standard_text"] = HOUSE[_c["key"]][1]


def _m(key, name, kcc_key, pattern, kind, unit, desc):
    return dict(key=key, name=name, kcc_key=kcc_key, pattern=pattern, kind=kind, unit=unit, description=desc, scale=1, enabled=True, builtin=False)


METRICS = [
    _m("laundry_rate_per_kg", "Laundry rate per kilogram", None, r"USD\s*([\d.]+)\s*per kilogram", "number", "USD/kg", "Price per kilogram of linen laundered"),
    _m("response_time_hours", "Fault response time", "service_response", r"within\s+(?:[a-z\-]+\s*)?\(?(\d+)\)?\s*hours?", "number", "hours", "Hours to attend a fault report"),
    _m("commission_pct", "Booking commission", "distribution_commission", r"(\d+(?:\.\d+)?)\s*(?:percent|%)", "number", "% of room revenue", "Commission on bookings through a channel"),
]


def _r(key, name, desc, rtype, sev, applies, **kw):
    return dict(key=key, name=name, description=desc, rule_type=rtype, kcc_key=kw.get("kcc"), metric_key=kw.get("metric"), operator=kw.get("op"), threshold=kw.get("num"), threshold_text=None,
                phrase=kw.get("phrase"), severity=sev, applies_to=applies, categories=kw.get("cats") or [], stage="any", suggested_text=kw.get("fix"), enabled=True, builtin=False)


RULES = [
    _r("hotel_response_time_max", "Fault response within 4 hours", "Guests cannot wait: faults must be attended within 4 hours.", "metric_threshold", "medium", ["MSA", "SOW"], metric="response_time_hours", op="<=", num=4,
       fix="The Supplier shall respond to a fault report within 4 hours."),
    _r("hotel_commission_max", "Booking commission at most 15%", "Distribution commission above 15 percent of room revenue needs approval.", "metric_threshold", "high", ["SaaS"], metric="commission_pct", op="<=", num=15,
       fix="The commission payable on each booking shall not exceed 15 percent of room revenue."),
    _r("hotel_renewal_notice_max", "Renewal notice at most 90 days", "A hotel needs a short, workable window to stop an auto-renewal (seasonal budgets change).", "metric_threshold", "high", ["MSA", "SOW", "SaaS"],
       metric="renewal_notice_days", op="<=", num=90, fix="The agreement renews automatically unless a party gives at least 60 days' written notice of non-renewal."),
    _r("hotel_liability_cap_min", "Supplier liability cap at least 1x annual fees", "A supplier whose staff or systems can harm guests must stand behind at least a year's fees.", "metric_threshold", "high", ["MSA", "SaaS", "SOW"],
       metric="liability_cap_multiple", op=">=", num=1, fix="The Supplier's aggregate liability is limited to one (1) times the fees paid or payable in the twelve months preceding the claim."),
    _r("hotel_pci_required", "Payment-card security present", "Required where a supplier handles card data.", "clause_required", "critical", ["SaaS"], kcc="payment_card_data", cats=["Hotel Technology", "Distribution & Booking"], fix=CLAUSES[6]["standard_text"]),
    # asked only of the kind of supplier they concern
    _r("hotel_food_safety", "Food-safety certification (food suppliers)", "A supplier of food or drink must hold food-safety certification and report recalls.", "clause_required", "critical", ["MSA", "SOW"],
       kcc="food_safety", cats=["Food & Beverage Supply"], fix=CLAUSES[0]["standard_text"]),
    _r("hotel_inspections", "Statutory inspection certificates (lifts, plant)", "Lift and plant contractors must deliver the statutory inspection certificates.", "clause_required", "high", ["MSA"],
       kcc="inspection_certificates", cats=["Lifts & Engineering", "Facilities & HVAC"], fix=CLAUSES[8]["standard_text"]),
    _r("hotel_guest_injury", "Guest-injury indemnity (suppliers working on site)", "A supplier whose people or equipment are in the hotel indemnifies it for injury to guests and staff.", "clause_required", "high", ["MSA"],
       kcc="guest_injury_indemnity", cats=["Security", "Lifts & Engineering", "Facilities & HVAC", "Pest Control", "Staffing", "Food & Beverage Supply", "Laundry & Linen"], fix=CLAUSES[1]["standard_text"]),
    _r("hotel_sale_termination", "Exit on sale of property", "Hotel groups buy and sell hotels: every property contract needs an exit on sale.", "clause_required", "medium", ["MSA"], kcc="property_sale_termination", fix=CLAUSES[3]["standard_text"]),
    _r("hotel_labour_compliance", "Labour and wage compliance clause present", "Staffing and security suppliers must commit to wage and working-time law.", "clause_required", "medium", ["MSA"], kcc="labour_compliance", cats=["Staffing", "Security", "Laundry & Linen", "Facilities & HVAC", "Waste & Sustainability"], fix=CLAUSES[2]["standard_text"]),
]


def ensure(s) -> dict:
    """Idempotently add the hospitality clauses, values and rules (never overwrites an admin's edits)."""
    kcc.ensure_defaults(s)
    out = {"kcc": kcc._insert_missing(s, "kcc_library", kcc.KCC_COLS, CLAUSES),
           "metrics": kcc._insert_missing(s, "metrics", kcc.MET_COLS, METRICS)}
    rules = [dict(r, sort_order=900 + i) for i, r in enumerate(RULES)]
    out["rules"] = kcc._insert_missing(s, "checklist_rules", kcc.RULE_COLS + ["categories", "sort_order"], rules)
    for r in rules:           # pack rules are admin rows: bring their scope up to date on re-seed without touching a rule an admin created
        s.execute(text("UPDATE checklist_rules SET categories = :c WHERE key = :k AND NOT builtin AND categories = '{}'"), {"c": r["categories"], "k": r["key"]})
    s.execute(text("UPDATE checklist_rules SET enabled=false WHERE key='governing_law_ny'"))     # a hotel group is not tied to one state's law: Legal decides per vendor
    for m in METRICS:         # pack metrics are admin rows: bring their patterns up to date on re-seed, without touching a metric an admin created
        s.execute(text("UPDATE metrics SET pattern=:p WHERE key=:k AND NOT builtin"), {"p": m["pattern"], "k": m["key"]})
    kcc.rebuild_key_clauses_view(s)
    return out
