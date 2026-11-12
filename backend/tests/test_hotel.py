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
