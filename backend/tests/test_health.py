from fastapi.testclient import TestClient

from app.main import app


def test_health_requires_db_reachable(monkeypatch):
    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, stmt):
            class R:
                def scalar(self_):
                    return 1

            return R()

    monkeypatch.setattr("app.main.engine", type("E", (), {"connect": lambda s: FakeConn()})())
    r = TestClient(app).get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
