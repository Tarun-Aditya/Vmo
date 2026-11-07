import os
import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

os.environ["LLM_PROVIDER"] = "offline"      # tests are deterministic: no LLM, whatever is installed
os.environ.setdefault("SIMULATORS", "1")       # the built-in ERP and e-signature stand-ins are mounted so their tests can run
os.environ.setdefault("SIM_IMAP_PORT", "11430")
os.environ.setdefault("SIM_SMTP_PORT", "25250")


@pytest.fixture(scope="session")
def db():
    """A real DB connection, or skip (unit tests above don't need one)."""
    from app.db import engine

    try:
        with engine.connect() as c:
            c.execute(text("select 1"))
    except Exception:
        pytest.skip("database not reachable")
    return engine


@pytest.fixture(scope="session")
def seeded(db):
    with db.connect() as c:
        if c.execute(text("select count(*) from contracts")).scalar() < 27:
            pytest.skip("database not seeded (run `make seed`)")
    return True


@pytest.fixture
def clean_docs(seeded):
    """Remove anything a test creates (generated/uploaded/test documents) so the seeded corpus stays pristine."""
    from app.db import SessionLocal
    from app.pipeline import inbox_path

    def wipe():
        with SessionLocal() as s:
            root = inbox_path(s)
            s.execute(text("DELETE FROM contracts WHERE origin IN ('generated','upload') OR source_path LIKE 'pytest/%'"))
            s.commit()
        for sub in ("generated", "uploads"):
            shutil.rmtree(root / sub, ignore_errors=True)

    wipe()
    yield
    wipe()


@pytest.fixture
def client(seeded):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def tmp_inbox(tmp_path: Path, monkeypatch, clean_docs):
    """Point the pipeline at a temporary folder; documents ingested from it use the 'pytest/' prefix."""
    from app import pipeline
    from app.db import SessionLocal

    root = tmp_path / "pytest"
    root.mkdir()
    monkeypatch.setattr(pipeline, "inbox_path", lambda s=None: tmp_path)
    yield root
    with SessionLocal() as s:
        s.execute(text("DELETE FROM contracts WHERE source_path LIKE 'pytest/%'"))
        s.commit()
