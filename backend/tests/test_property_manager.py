"""Property managers: a user limited to one property sees that property only (screens, records, Ask's own database queries), alerts reach the channel of the
property they concern, service calls are held to the response time the contract promises, and supplier contacts belong to a property."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.db import SessionLocal

HARBOR, LODGE = "PM Harbor Hotel", "PM Lodge"
CLAUSE = "The Supplier shall attend a passenger entrapment within 1 hour, and any other elevator fault within 4 hours of a report."


def _ins(s, table, **kw):
    return s.execute(text(f"INSERT INTO {table} ({', '.join(kw)}) VALUES ({', '.join(':' + k for k in kw)}) RETURNING id"), kw).scalar()


@pytest.fixture()
def hotels(seeded):
    """Two properties; an elevator MSA with a schedule at each (the Harbor one promises 1 h / 4 h); committed, removed afterwards."""
    with SessionLocal() as s:
        for p in (HARBOR, LODGE):
            s.execute(text("INSERT INTO properties (name, rooms) VALUES (:p, 100) ON CONFLICT DO NOTHING"), {"p": p})
        msa = _ins(s, "contracts", title="PM Elevator MSA", vendor="PM Lifts Inc", category="Elevators", type="MSA", status="active")
        h = _ins(s, "contracts", title="PM SOW Harbor", vendor="PM Lifts Inc", category="Elevators", type="SOW", status="active", parent_id=msa, property=HARBOR, annual_value=50000)
        lo = _ins(s, "contracts", title="PM SOW Lodge", vendor="PM Lifts Inc", category="Elevators", type="SOW", status="active", parent_id=msa, property=LODGE, annual_value=40000)
        other = _ins(s, "contracts", title="PM Lodge Laundry", vendor="PM Linen Inc", category="Laundry", type="SOW", status="active", property=LODGE, annual_value=9000)
        cl = _ins(s, "clauses", contract_id=h, clause_type="service_response", heading="Response times", text=CLAUSE, page=2)
        s.execute(text("INSERT INTO extracted_values (contract_id, metric_key, value_num, clause_id, page) VALUES (:c, 'response_time_hours', 1, :cl, 2)"), {"c": h, "cl": cl})
        s.commit()
    yield dict(msa=msa, harbor=h, lodge=lo, other=other)
    with SessionLocal() as s:
        s.execute(text("DELETE FROM service_events WHERE property IN (:a, :b)"), {"a": HARBOR, "b": LODGE})
        s.execute(text("DELETE FROM vendor_contacts WHERE vendor IN ('PM Lifts Inc', 'PM Linen Inc')"))
        s.execute(text("DELETE FROM alert_channels WHERE name LIKE 'PM %'"))
        s.execute(text("DELETE FROM contracts WHERE vendor IN ('PM Lifts Inc', 'PM Linen Inc')"))
        s.execute(text("DELETE FROM properties WHERE name IN (:a, :b)"), {"a": HARBOR, "b": LODGE})
        s.commit()


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def manager(client, hotels, monkeypatch):
    """AUTH_MODE=on with an administrator and a reviewer limited to the Harbor hotel."""
    def wipe():
        with SessionLocal() as s:
            for t in ("api_tokens", "users", "audit_log"):
                s.execute(text(f"DELETE FROM {t}"))
            s.execute(text("DELETE FROM conversations WHERE owner IS NOT NULL"))
            s.commit()
    wipe()
    monkeypatch.setenv("AUTH_MODE", "on")
    adm = H(client.post("/api/auth/bootstrap", json={"email": "root@hotel.test", "password": "correct-horse", "name": "Root"}).json()["token"])
    assert client.post("/api/users", headers=adm, json={"email": "admin2@hotel.test", "password": "password-1", "role": "admin", "property": HARBOR}).status_code == 422   # admins see everything
    assert client.post("/api/users", headers=adm, json={"email": "gm@hotel.test", "password": "password-1", "role": "reviewer", "property": "Nowhere"}).status_code == 422
    assert client.post("/api/users", headers=adm, json={"email": "gm@hotel.test", "password": "password-1", "role": "reviewer", "property": HARBOR}).status_code == 200
    gm = H(client.post("/api/auth/login", json={"email": "gm@hotel.test", "password": "password-1"}).json()["token"])
    yield client, adm, gm, hotels
    monkeypatch.delenv("AUTH_MODE")
    wipe()


def test_a_property_limited_account_sees_its_property_only(manager):
    c, adm, gm, ids = manager
    me = c.get("/api/auth/me", headers=gm).json()
    assert me["property"] == HARBOR and me["role"] == "reviewer"
    listed = {r["id"] for r in c.get("/api/contracts", headers=gm).json()}
    assert ids["harbor"] in listed and ids["msa"] in listed                  # its schedule and the master agreement covering it
    assert ids["lodge"] not in listed and ids["other"] not in listed          # nothing that applies only at the other hotel
    assert c.get(f"/api/contracts/{ids['harbor']}", headers=gm).status_code == 200
    assert c.get(f"/api/contracts/{ids['lodge']}", headers=gm).status_code == 403
    assert c.get(f"/api/contracts?property={LODGE}", headers=gm).status_code == 403          # asking for another property is refused, not ignored
    assert [p["property"] for p in c.get("/api/properties", headers=gm).json()["properties"]] == [HARBOR]
    assert c.get("/api/my-property", headers=gm).json()["property"] == HARBOR
    docs = {d["id"] for d in c.get("/api/documents", headers=gm).json()}          # Ask's document picker: this property's documents only
    assert ids["harbor"] in docs and ids["lodge"] not in docs
    for path in ("/api/dashboard", "/api/vendors", "/api/properties/compare", "/api/admin/kcc", "/api/risk/vendors", f"/api/documents/{ids['lodge']}/content",
                 f"/api/documents/{ids['harbor']}/content", "/api/templates"):
        assert c.get(path, headers=gm).status_code == 403, path          # every screen not on the allowed list is refused (deny by default)
    assert c.post("/api/renewals/decisions", headers=gm, json={"contract_id": ids["lodge"], "decision": "exit"}).status_code == 403
    assert {r["id"] for r in c.get("/api/contracts", headers=adm).json()} >= {ids["harbor"], ids["lodge"], ids["other"]}     # the administrator still sees every property


def test_asks_own_database_queries_cannot_see_another_property(hotels):
    from app import ask, scope

    tok = scope.SQL_LIMIT.set(scope.limit_for(HARBOR))
    try:
        got = {r[0] for r in ask.run_sql("SELECT id FROM contracts")["rows"]}
        assert hotels["harbor"] in got and hotels["lodge"] not in got and hotels["other"] not in got
        titles = {r[0] for r in ask.run_sql("SELECT title FROM v_effective_terms")["rows"]}
        assert "PM SOW Lodge" not in titles and "PM SOW Harbor" in titles
        assert ask.run_sql("SELECT name FROM properties")["rows"] == [[HARBOR]]
        assert "error" in ask.run_sql("SELECT id FROM public.contracts")         # no way round the limit by naming the schema
    finally:
        scope.SQL_LIMIT.reset(tok)
    assert hotels["lodge"] in {r[0] for r in ask.run_sql("SELECT id FROM contracts")["rows"]}       # without the limit (and on a new connection) everything is back


def test_service_calls_are_held_to_the_contract_promise(hotels):
    from app import onsite

    now = datetime.now(timezone.utc)
    with SessionLocal() as s:
        for kind, ago, att, what in (("emergency", 30, 1.5, "entrapment"), ("fault", 20, 3, "door"), ("fault", 10, 6, "levelling"), ("fault", 0.5, None, "still waiting")):
            rep = now - timedelta(hours=ago)
            s.execute(text("INSERT INTO service_events (property, vendor, kind, description, reported_at, attended_at) VALUES (:p, 'PM Lifts Inc', :k, :d, :r, :a)"),
                      {"p": HARBOR, "k": kind, "d": what, "r": rep, "a": rep + timedelta(hours=att) if att is not None else None})
        s.commit()
        sv = onsite.service(s, HARBOR)
    calls = {c["description"]: c for c in sv["calls"]}
    assert calls["entrapment"]["promised_hours"] == 1 and calls["entrapment"]["late"]            # an emergency is held to the shortest time in the clause
    assert calls["door"]["promised_hours"] == 4 and not calls["door"]["late"]
    assert calls["levelling"]["late"] and not calls["still waiting"]["late"]                     # 30 minutes waiting is not yet late
    v = next(x for x in sv["vendors"] if x["vendor"] == "PM Lifts Inc")
    assert (v["calls"], v["late"], v["open"], v["worst_hours"]) == (4, 2, 4, 6.0) and v["promise"]["contract_id"] == hotels["harbor"]


def test_alerts_reach_only_the_channel_of_their_property(hotels, monkeypatch):
    from app import alerts, scope

    with SessionLocal() as s:
        assert scope.alert_properties(s, hotels["lodge"], None) == [LODGE]
        assert set(scope.alert_properties(s, hotels["msa"], None)) == {HARBOR, LODGE}           # a group agreement concerns every property it covers
        for name, prop in (("PM Harbor desk", HARBOR), ("PM Lodge desk", LODGE), ("PM Group", None)):
            s.execute(text("INSERT INTO alert_channels (name, kind, config, min_severity, property) VALUES (:n, 'webhook', '{}', 'low', :p)"), {"n": name, "p": prop})
        s.execute(text("DELETE FROM alerts WHERE dedupe_key LIKE 'pm-test:%'"))
        s.commit()
    sent = []
    monkeypatch.setattr(alerts, "send", lambda ch, a: sent.append((ch["name"], a["title"])) or {"ok": True})
    monkeypatch.setattr(alerts, "_candidates", lambda s, r, today: [dict(dedupe="pm-test:1", title="Lodge only", contract_id=hotels["lodge"], vendor="PM Lifts Inc")]
                        if r["key"] == "obligation_overdue" else [])
    alerts.evaluate()
    got = {n for n, t in sent if t == "Lodge only" and n.startswith("PM ")}
    assert got == {"PM Lodge desk", "PM Group"}                                                    # not the Harbor desk
    with SessionLocal() as s:
        assert s.execute(text("SELECT properties FROM alerts WHERE dedupe_key = 'pm-test:1'")).scalar() == [LODGE]
        s.execute(text("DELETE FROM alerts WHERE dedupe_key LIKE 'pm-test:%'"))
        s.commit()


def test_a_manager_logs_calls_and_contacts_for_their_own_property(manager):
    c, adm, gm, ids = manager
    assert c.post("/api/service-events", headers=gm, json={"vendor": "PM Linen Inc", "kind": "fault"}).status_code == 422      # no contract of theirs at Harbor
    assert c.post("/api/service-events", headers=gm, json={"vendor": "PM Lifts Inc", "kind": "fault", "property": LODGE}).status_code == 403
    assert c.post("/api/service-events", headers=gm, json={"vendor": "PM Lifts Inc", "kind": "fault", "description": "lobby elevator"}).status_code == 200
    assert any(x["description"] == "lobby elevator" for x in c.get("/api/service-events", headers=gm).json()["calls"])
    assert c.post("/api/vendor-contacts", headers=gm, json={"vendor": "PM Lifts Inc", "name": "Dana", "phone": "555-0199", "property": LODGE}).status_code == 200
    mine = c.get("/api/vendor-contacts", headers=gm).json()
    assert [(x["name"], x["property"]) for x in mine if x["vendor"] == "PM Lifts Inc"] == [("Dana", HARBOR)]      # recorded for their own property whatever was sent
    page = c.get("/api/my-property", headers=gm).json()
    assert any(x["name"] == "Dana" for x in page["contacts"]) and page["property"] == HARBOR


def test_conversations_belong_to_their_owner(manager):
    c, adm, gm, ids = manager
    with SessionLocal() as s:
        mine = _ins(s, "conversations", title="gm question", owner="gm@hotel.test")
        theirs = _ins(s, "conversations", title="root question", owner="root@hotel.test")
        s.commit()
    listed = {x["id"] for x in c.get("/api/conversations", headers=gm).json()}
    assert mine in listed and theirs not in listed
    assert c.get(f"/api/conversations/{theirs}", headers=gm).status_code == 404
    with SessionLocal() as s:
        s.execute(text("DELETE FROM conversations WHERE id IN (:a, :b)"), {"a": mine, "b": theirs})
        s.commit()


def test_a_managers_chat_answer_stays_within_their_property(manager):
    c, adm, gm, ids = manager
    with c.stream("POST", "/api/chat/stream", headers=gm, json={"question": "Which contracts are there? Show the title of every contract.", "demo_mode": False}) as r:
        body = "".join(r.iter_text())
    assert r.status_code == 200 and "PM SOW Harbor" in body
    assert "PM SOW Lodge" not in body and "PM Lodge Laundry" not in body          # the other hotel's contracts never reach the answer
