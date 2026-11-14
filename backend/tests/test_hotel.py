"""Property level: PDF tables, signature blocks, properties and their share of group agreements, cross-property comparison, certificates."""
from datetime import date, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import certificates, properties
from app.ask_nl import _lit
from app.docstruct import merge_layout_tables
from app.extract_rules import Doc, signatures

TABLE = """3. Deliverables and Milestones
                         Deliverable /
 No.                     Milestone                Due Date                Acceptance Criteria
 Milestone 1             Planned-                 27 November 2025        Schedule approved in
                         maintenance                                      writing by the
                         schedule agreed                                  Customer's Property
                                                                          representative
 Milestone 2             Chiller replacement      22 December 2026        Chiller installed,
                         complete                                         commissioned and tested

3.1 The Supplier shall use reasonable endeavours to meet each due date."""


def test_pdf_table_rows_are_rebuilt_with_wrapped_cells_joined():
    out = merge_layout_tables(TABLE).split("\n")
    assert out[0] == "3. Deliverables and Milestones"                      # the heading above the table is not swallowed into it
    assert out[1] == "| No. | Deliverable / Milestone | Due Date | Acceptance Criteria |"
    assert out[2] == "| Milestone 1 | Planned-maintenance schedule agreed | 27 November 2025 | Schedule approved in writing by the Customer's Property representative |"
    assert out[3].startswith("| Milestone 2 | Chiller replacement complete | 22 December 2026 |")
    assert out[-1].startswith("3.1 The Supplier")


def test_two_column_signature_layout_and_prose_are_left_alone():
    sig = "Name                      Helena Cruz\nTitle                     VP Sourcing\n\nPlain paragraph of text that is not a table at all."
    assert merge_layout_tables(sig) == sig


def _sig(md):
    return signatures(Doc(md, {}, [], "MSA"))


def test_signed_sentence_wrapped_over_lines(monkeypatch):
    monkeypatch.setattr("app.extract_rules.customer_markers", lambda: ["seabright"])
    md = ("## Execution\nSigned for and on behalf of Seabright Hotels & Resorts Ltd by Helena Cruz, VP Technology\nSourcing, on 07 January 2024.\nSignature: ______\n"
          "Signed for and on behalf of Lumen Energy Supply Ltd by Anika Rao, Authorised Signatory, on\n10 January 2024.\nSignature: ______\n")
    c, s = _sig(md)
    assert c == ("Helena Cruz", date(2024, 1, 7)) and s == ("Anika Rao", date(2024, 1, 10))


def test_signed_sentence_with_date_on_its_own_line(monkeypatch):
    monkeypatch.setattr("app.extract_rules.customer_markers", lambda: ["seabright"])
    md = ("## Signatures\nSigned for and on behalf of Seabright Hotels & Resorts Ltd by Helena Cruz, VP Technology\nSourcing\nSignature: ______________________\nDate: 11 May 2025\n"
          "Signed for and on behalf of Crestline Laundry & Linen Services Ltd by Grace Mbeki,\nAuthorised Signatory\nSignature: ______________________\nDate: 14 May 2025\n")
    c, s = _sig(md)
    assert c == ("Helena Cruz", date(2025, 5, 11)) and s == ("Grace Mbeki", date(2025, 5, 14))


def test_signature_table_with_dates_but_blank_names_counts_as_signed(monkeypatch):
    monkeypatch.setattr("app.extract_rules.customer_markers", lambda: ["seabright"])
    md = ("## Execution\n\nSigned by the duly authorised representatives of the Parties.\n\n"
          "                          **Seabright Hotels & Resorts Ltd**   **Crestline Laundry & Linen Services Ltd**\n"
          "  Signature\n\n  Name\n\n  Title\n\n  Date                    05 June 2026                         08 June 2026\n")
    c, s = _sig(md)
    assert c and s and c[1] == date(2026, 6, 5) and s[1] == date(2026, 6, 8)
    unsigned = md.replace("05 June 2026", "            ").replace("08 June 2026", "")
    assert _sig(unsigned) == (None, None)


def test_sql_literal_escapes_quotes():
    assert _lit("O'Brien Catering") == "'O''Brien Catering'"


def test_certificate_status():
    t = date(2026, 6, 1)
    assert certificates.status(None, t) == "missing"
    assert certificates.status(t - timedelta(days=1), t) == "expired"
    assert certificates.status(t + timedelta(days=certificates.SOON_DAYS), t) == "expiring"
    assert certificates.status(t + timedelta(days=certificates.SOON_DAYS + 1), t) == "valid"


def _contract(c, **kw):
    kw = {"status": "active", **kw}
    return c.execute(text(f"INSERT INTO contracts ({', '.join(kw)}) VALUES ({', '.join(':' + k for k in kw)}) RETURNING id"), kw).scalar()


def _world(c):
    """Two properties (300 and 100 rooms); a vendor with a group MSA and a schedule at each property; a group-wide energy contract; an NDA."""
    c.execute(text("DELETE FROM contract_coverage; DELETE FROM properties"))
    c.execute(text("UPDATE contracts SET status = 'draft'"))           # only this test's rows count (rolled back afterwards)
    a = c.execute(text("INSERT INTO properties (name, rooms) VALUES ('Test Harbour', 300) RETURNING id")).scalar()
    b = c.execute(text("INSERT INTO properties (name, rooms) VALUES ('Test Lodge', 100) RETURNING id")).scalar()
    msa = _contract(c, title="Laundry MSA", vendor="Linen Co", category="Laundry", type="MSA", annual_value=40000)
    s1 = _contract(c, title="SOW Harbour", vendor="Linen Co", category="Laundry", type="SOW", parent_id=msa, property="Test Harbour", annual_value=300000, payment_terms_days=45)
    s2 = _contract(c, title="SOW Lodge", vendor="Linen Co", category="Laundry", type="SOW", parent_id=msa, property="Test Lodge", annual_value=120000, payment_terms_days=30)
    energy = _contract(c, title="Energy", vendor="Power Co", category="Energy", type="MSA", annual_value=800000)
    _contract(c, title="NDA", vendor="Linen Co", category="Laundry", type="NDA")
    return dict(a=a, b=b, msa=msa, s1=s1, s2=s2, energy=energy)


def test_group_agreements_are_attributed_to_properties_by_rooms(db):
    with db.connect() as c:
        t = c.begin()
        w = _world(c)
        rows = {(r.property, r.contract_id): r for r in c.execute(text("SELECT * FROM v_property_contracts"))}
        assert rows[("Test Harbour", w["s1"])].basis == "named" and float(rows[("Test Harbour", w["s1"])].share) == 1
        assert rows[("Test Harbour", w["energy"])].basis == "group" and round(float(rows[("Test Harbour", w["energy"])].share), 2) == 0.75      # 300 of 400 rooms
        assert round(float(rows[("Test Lodge", w["energy"])].share), 2) == 0.25
        assert rows[("Test Lodge", w["msa"])].basis == "children"                 # the laundry MSA covers the properties its schedules name
        assert not any(r.title == "NDA" for r in rows.values())
        total = c.execute(text("SELECT sum(contract_annual_value * share) FROM v_property_contracts")).scalar()
        assert round(float(total)) == 40000 + 300000 + 120000 + 800000                # every dollar lands on exactly one property
        c.execute(text("INSERT INTO contract_coverage VALUES (:c, :p)"), {"c": w["energy"], "p": w["b"]})      # a person states the energy contract is for the lodge only
        cov = c.execute(text("SELECT property, basis, share FROM v_property_contracts WHERE contract_id = :c"), {"c": w["energy"]}).all()
        assert [(r.property, r.basis, float(r.share)) for r in cov] == [("Test Lodge", "stated", 1.0)]
        t.rollback()


def test_overview_and_compare(db):
    with db.connect() as c:
        t = c.begin()
        w = _world(c)
        c.execute(text("INSERT INTO metrics (key, name, pattern, kind, unit, enabled, builtin) VALUES ('t_rate', 'Test rate', 'x', 'number', 'USD/kg', true, false) ON CONFLICT DO NOTHING"))
        for cid, v in ((w["s1"], 1.50), (w["s2"], 1.20)):
            c.execute(text("INSERT INTO extracted_values (contract_id, metric_key, value_num) VALUES (:c, 't_rate', :v)"), {"c": cid, "v": v})
        s = Session(bind=c)
        ov = {p["property"]: p for p in properties.overview(s)["properties"]}
        assert round(float(ov["Test Harbour"]["annual_value"])) == 300000 + 30000 + 600000 and ov["Test Harbour"]["named_contracts"] == 1
        assert ov["Test Harbour"]["value_per_room"] == 3100.0
        cmp_ = properties.compare(s)
        linen = next(b for b in cmp_["same_vendor"] if b["vendor"] == "Linen Co")
        rate = next(m for m in linen["measures"] if m["key"] == "t_rate")
        assert rate["best"] == 1.2 and rate["spread_pct"] == 25.0 and [p["property"] for p in rate["points"]] == ["Test Lodge", "Test Harbour"]
        assert rate["saving_estimate"] == 60000            # Harbour at the Lodge's rate: 300,000 x (1 - 1.20 / 1.50)
        assert cmp_["saving_estimate"] == 60000
        t.rollback()


def test_required_certificates_follow_the_clauses_and_keep_what_was_recorded(db):
    with db.connect() as c:
        t = c.begin()
        w = _world(c)
        c.execute(text("DELETE FROM certificates"))
        c.execute(text("INSERT INTO clauses (contract_id, clause_type, text, page) VALUES (:c, 'insurance', 'cover', 3), (:c, 'food_safety', 'haccp', 4), "
                       "(:c, 'inspection_certificates', 'annual attestation of compliance', 5)"), {"c": w["msa"]})      # the last is a PCI attestation, not an inspection
        s = Session(bind=c)
        assert certificates.sync(s) == 2
        got = certificates.listing(s)
        assert {(r["vendor"], r["kind"], r["status"]) for r in got["certificates"]} == {("Linen Co", "insurance", "missing"), ("Linen Co", "food_safety", "missing")}
        c.execute(text("UPDATE certificates SET expiry_date = current_date - 3, source = 'person' WHERE kind = 'food_safety'"))
        c.execute(text("DELETE FROM clauses WHERE contract_id = :c"), {"c": w["msa"]})
        certificates.sync(s)                                       # the requirement is gone: the untouched row goes, the recorded one stays
        left = certificates.listing(s)["certificates"]
        assert [(r["kind"], r["status"]) for r in left] == [("food_safety", "expired")]
        t.rollback()


def test_invoice_with_no_matching_agreement_says_what_is_on_file(db):
    from app import spend

    with db.connect() as c:
        t = c.begin()
        _world(c)
        c.execute(text("DELETE FROM invoices"))
        c.execute(text("INSERT INTO invoices (external_id, vendor, invoice_no, invoice_date, amount) VALUES ('t-l1', 'Linen Co', 'L-1', current_date, 500), ('t-n1', 'Nobody Ltd', 'N-1', current_date, 70)"))
        s = Session(bind=c)
        spend.compute_exceptions(s)
        d = dict(c.execute(text("SELECT vendor, detail FROM spend_exceptions WHERE kind = 'no_contract'")).all())
        assert "does not match any of the 4 agreements on file" in d["Linen Co"]
        assert "no agreement of any kind is on file" in d["Nobody Ltd"]
        t.rollback()


def test_a_rule_for_one_vendor_category_is_not_asked_of_the_others():
    from app import kcc

    rule = dict(key="food", name="Food safety", rule_type="clause_required", kcc_key="food_safety", metric_key=None, operator=None, threshold=None, threshold_text=None, phrase=None,
                severity="critical", applies_to=["MSA"], categories=["Food & Beverage Supply"], stage="any", suggested_text=None)
    run = lambda cat, clauses: kcc.evaluate_rules("MSA", "active", clauses, [], [], [rule], True, category=cat)      # noqa: E731
    assert run("Lifts & Engineering", []) == []                                           # a lift contractor is not failed for having no food-safety clause
    assert [r["status"] for r in run("Food & Beverage Supply", [])] == ["fail"]
    assert [r["status"] for r in run("Food & Beverage Supply", [dict(clause_type="food_safety", text="HACCP", page=2)])] == ["pass"]
    assert [r["status"] for r in kcc.evaluate_rules("MSA", "active", [], [], [], [dict(rule, categories=[])], True, category="Lifts & Engineering")] == ["fail"]      # no scope = everyone


def test_governing_law_is_not_the_state_a_party_was_formed_in():
    from app.extract_rules import _governing_law

    assert _governing_law("Acme Inc, a corporation organized under the laws of the State of Delaware. This Agreement shall be governed by the laws of the State of New York.") == "New York"
    assert _governing_law("Acme, organized under the laws of Delaware, agrees this Agreement is governed by the laws of England and Wales.") == "England and Wales"
    assert _governing_law("Acme Inc, a company incorporated under the laws of Delaware. Fees are payable monthly.") is None
    assert _governing_law("This Agreement is made under the laws of the State of Texas.") == "Texas"


def test_spend_alerts_are_grouped_and_closed_when_the_cause_goes(db):
    from app import alerts

    rule = dict(key="spend_exception", kind="spend_exception", params={"min_severity": "high"}, severity="high")
    with db.connect() as c:
        t = c.begin()
        c.execute(text("DELETE FROM spend_exceptions"))
        for n in range(3):
            c.execute(text("INSERT INTO spend_exceptions (vendor, kind, severity, amount_at_risk, detail) VALUES ('Linen Co', 'duplicate', 'high', 100, :d)"), {"d": f"Invoice {n} repeats."})
        c.execute(text("INSERT INTO spend_exceptions (vendor, kind, severity, amount_at_risk, detail) VALUES ('Linen Co', 'late_payment', 'low', 5, 'late')"))
        got = alerts._candidates(Session(bind=c), rule, date.today())
        assert len(got) == 1 and got[0]["title"] == "3 spend exceptions (high): duplicate — Linen Co, $300"        # three invoices, one thing to chase; the low one raises nothing
        t.rollback()


def test_certificate_alerts(db):
    from app import alerts

    rule = dict(key="certificate_expiry", kind="certificate", params={"days": 30}, severity="high")
    with db.connect() as c:
        t = c.begin()
        c.execute(text("DELETE FROM certificates"))
        for kind, days in (("insurance", -3), ("food_safety", 10), ("payment_card_data", 45), ("inspection_certificates", None)):
            c.execute(text("INSERT INTO certificates (vendor, kind, name, expiry_date) VALUES ('Linen Co', :k, :k, :e)"), {"k": kind, "e": (date.today() + timedelta(days=days)) if days is not None else None})
        got = {a["title"].split(":")[0]: a["severity"] for a in alerts._candidates(Session(bind=c), rule, date.today())}
        assert got == {"insurance expired 3 days ago": "critical", "food_safety expires in 10 days": "high"}        # 45 days away and 'not on file' do not alert
        t.rollback()


def test_certificate_documents_are_read(monkeypatch):
    from app import opsdocs
    from app.docgen import hotel_spec

    monkeypatch.setattr("app.opsdocs.customer_markers", lambda: ["seabright"])
    for kind, vendor in (("insurance", "Northgate Facilities & HVAC Inc"), ("food_safety", "Hearth & Table Foods Inc"), ("inspection_certificates", "Halcyon Elevator & Lift Maintenance Inc"),
                         ("payment_card_data", "PayGuard Payments Inc")):
        t = opsdocs._clean(hotel_spec.certificate_md(vendor, kind, date(2027, 3, 5), date(2026, 3, 5), "REF-1234"))
        assert opsdocs.kind_of(t) == "certificate"
        got = opsdocs.parse_certificate(t)
        assert (got["vendor"], got["kind"], got["expiry_date"], got["received_on"], got["reference"]) == (vendor, kind, date(2027, 3, 5), date(2026, 3, 5), "REF-1234")      # the insured, never us
    assert opsdocs.kind_of("ACCEPTANCE CERTIFICATE\nMilestone: go-live") == "acceptance"            # a milestone sign-off is not a compliance certificate
    ins = opsdocs._clean(hotel_spec.certificate_md("Halcyon Elevator & Lift Maintenance Inc", "insurance", date(2027, 3, 5), date(2026, 3, 5), "POL-1"))
    assert opsdocs.parse_certificate(ins)["kind"] == "insurance"                                    # the holder's name does not decide the kind


def test_missing_library_clauses_are_findings_only_where_the_house_requires_them():
    from app import deviations

    lib = [dict(key=k, name=k, builtin=False, enabled=True, standard_text="Standard wording.", applies_to=["MSA"], severity_if_missing=sev, playbook_position="")
           for k, sev in (("food_safety", "high"), ("seasonal_pricing", "medium"), ("guest_injury_indemnity", "high"), ("brand_standards", "medium"))]
    rules = [dict(key="r_food", rule_type="clause_required", kcc_key="food_safety"), dict(key="r_injury", rule_type="clause_required", kcc_key="guest_injury_indemnity")]
    results = [dict(rule_key="r_injury", status="fail")]                      # food safety is not asked of this vendor's category: no result for r_food
    got = deviations.compare_custom([], lib, "MSA", skip={"brand_standards"}, rules=rules, results=results)
    assert [i["clause_type"] for i in got] == ["guest_injury_indemnity"]      # not food safety (rule does not apply), not seasonal pricing (optional), not brand standards (in the template)
    assert len(deviations.compare_custom([], lib, "MSA")) == 4                # without rules the old behaviour is unchanged


def test_claude_redline_keeps_its_findings_and_gains_any_failed_rule():
    from app import deviations

    claude = [dict(clause_type="payment", heading="Payment", status="changed", draft_text="pay in 10 days", standard_text="pay in 45 days", severity="high", deviation="shorter")]
    rules = [dict(key="renewal_max", name="Renewal notice at most 90 days", description="", kcc_key=None, metric_key="renewal_notice_days", suggested_text="At least 60 days.", severity="high"),
             dict(key="pay", name="Payment terms", description="", kcc_key="payment", metric_key=None, suggested_text="", severity="high")]
    results = [dict(rule_key="renewal_max", status="fail", actual="180", expected="<= 90", severity="high", clause_id=None), dict(rule_key="pay", status="fail", actual="10", expected=">= 30", severity="high", clause_id=None)]
    metrics = [dict(key="renewal_notice_days", kcc_key="renewal")]
    out = deviations.playbook_items(claude, results, rules, metrics, [dict(id=1, clause_type="renewal", text="renews unless 180 days notice", page=2)], [dict(key="renewal", name="Renewal")], keep_all=True)
    assert [i["clause_type"] for i in out] == ["payment", "renewal"]          # Claude's payment finding once, plus the renewal rule it did not raise
    assert out[0]["deviation"] == "shorter" and "180" in out[1]["deviation"]


def test_a_partys_legal_form_is_not_the_vendor(monkeypatch):
    from app import meta_rules

    monkeypatch.setattr("app.meta_rules.customer_markers", lambda: ["seabright"])
    md = ('# Master Services Agreement\n\nThis Agreement is made between:\n\n(1) **Seabright Hotels & Resorts Inc**, a Delaware corporation, which owns and operates six hotels (the "Client"); and\n\n'
          '(2) **Crestline Laundry & Linen Services Inc**, a Delaware corporation (the "Supplier").\n')
    assert meta_rules.find_vendor(md, {}, {}) == "Crestline Laundry & Linen Services Inc"
    llc = 'This Agreement is entered into by and between Seabright Hotels & Resorts Inc and Blue Peak Services LLC, a New York limited liability company.'
    assert meta_rules.find_vendor(llc, {}, {}) == "Blue Peak Services LLC"


def test_how_each_contract_can_be_exited_on_a_sale(db):
    with db.connect() as c:
        t = c.begin()
        w = _world(c)
        c.execute(text("UPDATE contracts SET termination_for_convenience = true WHERE id = :i"), {"i": w["msa"]})                 # the laundry MSA can be ended on notice
        c.execute(text("UPDATE contracts SET termination_for_convenience = false, expiry_date = current_date + 365 WHERE id = :i"), {"i": w["energy"]})
        c.execute(text("INSERT INTO clauses (contract_id, clause_type, text, page) VALUES (:c, 'property_sale_termination', 'If a Property is sold the Customer may terminate.', 6)"), {"c": w["s2"]})
        s = Session(bind=c)
        ex = properties.exit_terms(s)
        assert ex[w["s1"]]["exit"] == "notice" and ex[w["s1"]]["exit_from"] == "its master agreement"       # a schedule that is silent follows its master agreement
        assert ex[w["s2"]]["exit"] == "sale" and ex[w["s2"]]["exit_from"] == "this contract"
        assert ex[w["energy"]]["exit"] == "locked"
        d = properties.detail(s, w["a"])
        assert d["sale"]["locked_contracts"] == 1 and round(d["sale"]["locked_value"]) == 600000            # 75% of the energy contract's year still to run
        t.rollback()
