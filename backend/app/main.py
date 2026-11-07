import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import kcc, scheduler
from app.db import SessionLocal, engine
from app.routes import router
from app.routes_admin import router as admin_router
from app.routes_chat import router as chat_router
from app.routes_connectors import router as connectors_router
from app.routes_docs import router as docs_router
from app.routes_vmo import router as vmo_router

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed missing config defaults, then run the pipeline scheduler in the background."""
    task = None
    try:
        with SessionLocal() as s:
            kcc.ensure_defaults(s)
            s.commit()
        if os.environ.get("SCHEDULER_ENABLED", "1") == "1":
            task = asyncio.create_task(scheduler.scheduler_loop())
    except Exception:  # DB not migrated yet: the API still starts, /health tells the story
        log.exception("startup config/scheduler not started")
    yield
    if task:
        task.cancel()


app = FastAPI(title="ContractIQ API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(admin_router)
app.include_router(docs_router)
app.include_router(chat_router)
app.include_router(connectors_router)
app.include_router(vmo_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Green only if the DB is reachable and pgvector is installed."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        vec = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()
    return {"status": "ok", "db": "ok", "pgvector": "ok" if vec else "missing"}
