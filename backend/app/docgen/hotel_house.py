"""The hotel group's own clauses in its standard templates (STANDARDS=hotel): wording that applies to every supplier working at a property, whatever it supplies.
Category-specific clauses (food safety for a food supplier, statutory inspections for a lift contractor) stay in the hospitality pack as key clauses and
checklist rules, because a template that demanded them of every supplier would report a 'missing clause' on contracts that have no need of one.
key -> (heading, standard wording, negotiating position, severity if missing, template types that carry it)."""
from __future__ import annotations

HOUSE: dict[str, tuple[str, str, str, str, tuple[str, ...]]] = {
    "guest_injury_indemnity": (
        "Guest and Staff Injury",
        "The Supplier shall indemnify the Customer against claims by guests or staff for injury, illness or death caused by the Supplier's acts, omissions or equipment.",
        "Required of every supplier whose people or equipment are on a property. Do not accept a cap below the insurance cover.", "high", ("MSA",)),
    "labour_compliance": (
        "Labour and Wage Compliance",
        "The Supplier shall pay all personnel at least the applicable minimum wage, comply with working-time rules and shall not use forced or underage labour.",
        "Required. A supplier's labour breach at a property becomes the hotel's reputational problem.", "medium", ("MSA",)),
    "property_sale_termination": (
        "Sale of Property",
        "The Customer may terminate the services at a Property on 30 days' notice, without penalty, if the Property is sold or ceases to be operated by the Customer.",
        "Required. The group buys and sells hotels; a contract that cannot be ended on a sale reduces the sale price. Accept up to 60 days' notice.", "medium", ("MSA",)),
    "brand_standards": (
        "Brand and Operating Standards",
        "The Supplier shall perform the services to the brand and operating standards notified by the Customer from time to time.",
        "Required. Accept 'reasonable' standards notified in writing with 30 days to comply with a change.", "medium", ("MSA",)),
    "payment_card_data": (
        "Payment Card Security",
        "The Supplier shall comply with PCI DSS wherever it stores, processes or transmits payment-card data and shall provide its annual attestation of compliance.",
        "Required of any system that touches card data. No fallback.", "critical", ("SaaS",)),
}
