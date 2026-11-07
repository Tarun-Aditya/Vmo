import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import auth, kcc, scheduler
from app.db import SessionLocal, engine
from app.routes import router
from app.routes_admin import router as admin_router
from app.routes_alerts import router as alerts_router
from app.routes_auth import router as auth_router
from app.routes_comments import router as comments_router
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
@app.middleware("http")
async def access_control(request: Request, call_next):
    """AUTH_MODE=on: every /api call needs a login or API token with a high enough role; every change (and every refusal) is written to the audit log."""
    path, method = request.url.path, request.method
    need = auth.required(method, path)
    user = None
    if auth.mode() == "on" and need is not None:
        h = request.headers.get("authorization", "")
        tok = h[7:] if h.lower().startswith("bearer ") else request.query_params.get("access_token")
        user = await run_in_threadpool(auth.identify, tok)
        if user is None or auth.RANK[user["role"]] < auth.RANK[need]:
            code = 401 if user is None else 403
            ip = request.client.host if request.client else None
            await run_in_threadpool(auth.audit, user, method, path, code, ip, "denied")
            return JSONResponse({"detail": "Sign in required" if code == 401 else f"This needs the {need} role"}, status_code=code)
        request.state.user = user
    resp = await call_next(request)
    if method not in ("GET", "HEAD", "OPTIONS") or "/export" in path:
        if not path.startswith("/api/auth/login") and not (path.startswith("/api/chat") and resp.status_code < 400):
            await run_in_threadpool(auth.audit, user, method, path, resp.status_code, request.client.host if request.client else None)
    return resp


app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(admin_router)
app.include_router(docs_router)
app.include_router(chat_router)
app.include_router(connectors_router)
app.include_router(alerts_router)
app.include_router(auth_router)
app.include_router(comments_router)
app.include_router(vmo_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Green only if the DB is reachable and pgvector is installed."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        vec = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()
    return {"status": "ok", "db": "ok", "pgvector": "ok" if vec else "missing"}
