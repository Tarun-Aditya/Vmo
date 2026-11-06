"""Renewal date math and effective-terms resolution, tested in a rolled-back transaction."""
from datetime import date, timedelta

from sqlalchemy import text


def _ins(c, **kw):
    cols = ", ".join(kw)
    vals = ", ".join(f":{k}" for k in kw)
    return c.execute(text(f"INSERT INTO contracts ({cols}) VALUES ({vals}) RETURNING id"), kw).scalar()


def test_notice_deadline_and_buckets(db):
    today = date.today()
    with db.connect() as c:
        t = c.begin()
        _ins(c, title="A", vendor="v", type="SaaS", expiry_date=today + timedelta(days=50),
             notice_period_days=30, auto_renew=True, annual_value=100)
        _ins(c, title="B", vendor="v", type="NDA", expiry_date=today + timedelta(days=10))
        _ins(c, title="C", vendor="v", type="SaaS", expiry_date=today + timedelta(days=20),
             notice_period_days=30, auto_renew=True)
        rows = {r.title: r for r in c.execute(text("SELECT * FROM v_renewals WHERE title IN ('A','B','C')"))}
        t.rollback()
    assert rows["A"].notice_deadline == today + timedelta(days=20)
    assert rows["A"].days_left == 50 and rows["A"].bucket == "30"   # bucketed by notice deadline
    assert rows["B"].bucket == "30" and rows["B"].notice_deadline == today + timedelta(days=10)
    assert rows["C"].bucket == "overdue" and rows["C"].notice_days_left == -10


def test_amendment_overrides_with_provenance_and_uncapped(db):
    today = date.today()
    with db.connect() as c:
        t = c.begin()
        msa = _ins(c, title="M", vendor="v", type="MSA", payment_terms_days=45,
                   liability_cap_multiple=1, liability_cap_text="1 times", expiry_date=today)
        _ins(c, title="A1", vendor="v", type="Amendment", parent_id=msa,
                  effective_date=today - timedelta(days=20), payment_terms_days=30,
                  overrides=["payment_terms_days"])
        a2 = _ins(c, title="A2", vendor="v", type="Amendment", parent_id=msa,
                  effective_date=today - timedelta(days=5), payment_terms_days=60,
                  liability_cap_text="Unlimited", overrides=["payment_terms_days", "liability_cap_multiple", "liability_cap_text"])
        r = c.execute(text("SELECT * FROM v_effective_terms WHERE contract_id=:i"), {"i": msa}).one()
        t.rollback()
    assert r.payment_terms_days == 60 and r.payment_terms_days_source == a2  # latest amendment wins
    assert r.liability_cap_multiple is None and r.liability_uncapped        # override TO null = uncapped
    assert r.expiry_date_source == msa                                      # untouched -> parent
