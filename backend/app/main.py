import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from app import auth, kcc, scheduler
from app.db import SessionLocal, engine
from app.routes import router
from app.routes_admin import router as admin_router
from app.routes_alerts import router as alerts_router
from app.routes_approvals import router as approvals_router
from app.routes_auth import router as auth_router
from app.routes_chat import router as chat_router
from app.routes_comments import router as comments_router
from app.routes_connectors import router as connectors_router
from app.routes_docs import router as docs_router
from app.routes_quality import router as quality_router
from app.routes_scim import router as scim_router
from app.routes_signatures import router as signatures_router
from app.routes_vmo import router as vmo_router
from app.routes_hotel import router as hotel_router

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Seed missing config defaults, then run the pipeline scheduler in the background."""
    task = None
    try:
        with SessionLocal() as s:
            kcc.ensure_defaults(s)
            s.commit()
        if os.environ.get("SIMULATORS", "0") == "1":
            try:
                from app.simulators import mail as sim_mail

                srv, _ = await sim_mail.serve_imap(int(os.environ.get("SIM_IMAP_PORT", "1143")))
                app.state.sim_imap = srv
                app.state.sim_smtp = sim_mail.start_smtp_sink(int(os.environ.get("SIM_SMTP_PORT", "2525")))
            except OSError:
                log.warning("simulated mail servers not started (port in use)")
        if os.environ.get("SCHEDULER_ENABLED", "1") == "1":
            task = asyncio.create_task(scheduler.scheduler_loop())
    except Exception:  # DB not migrated yet: the API still starts, /health tells the story
        log.exception("startup config/scheduler not started")
    yield
    if task:
        task.cancel()


app = FastAPI(title="ContractIQ API", version="0.2.0", lifespan=lifespan)
class JsonFormatter(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        import json as _j

        return _j.dumps({"ts": self.formatTime(r), "level": r.levelname, "logger": r.name, "msg": r.getMessage(), **({"exc": self.formatException(r.exc_info)} if r.exc_info else {})})


if os.environ.get("LOG_JSON") == "1":                      # one JSON object per line for log shippers
    _h = logging.StreamHandler()
    _h.setFormatter(JsonFormatter())
    logging.getLogger().handlers[:] = [_h]
    logging.getLogger().setLevel(logging.INFO)


@app.middleware("http")
async def request_id(request: Request, call_next):
    import time
    import uuid

    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    t0 = time.time()
    resp = await call_next(request)
    resp.headers["X-Request-ID"] = rid
    if request.url.path.startswith("/api/") and (resp.status_code >= 500 or time.time() - t0 > 5):
        log.warning("slow or failed request %s %s -> %s in %.1fs [%s]", request.method, request.url.path, resp.status_code, time.time() - t0, rid)
    return resp


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault("Cache-Control", "no-store") if request.url.path.startswith("/api/") else None
    if os.environ.get("HSTS", "0") == "1":
        resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return resp


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
app.include_router(approvals_router)
app.include_router(signatures_router)
app.include_router(quality_router)
app.include_router(scim_router)
if os.environ.get('SIMULATORS', '0') == '1':        # stand-ins for ERP and e-signature services, for demos and tests only
    from app.simulators.erp import router as sim_erp
    from app.simulators.esign import router as sim_esign

    app.include_router(sim_erp)
    app.include_router(sim_esign)
    from app.simulators import cloud as sim_cloud
    from app.simulators import mail as sim_mail
    from app.simulators import sso as sim_sso

    app.include_router(sim_mail.router)
    app.include_router(sim_sso.idp)
    app.mount('/sim/gdrive', sim_cloud.Lazy(0))
    app.mount('/sim/graph', sim_cloud.Lazy(1))
app.include_router(vmo_router)
app.include_router(hotel_router)


_addin = Path(__file__).resolve().parents[2] / "addin"
if _addin.exists():                       # the Word task pane (needs HTTPS in production: put the API behind your TLS proxy)
    app.mount("/addin", StaticFiles(directory=_addin), name="addin")


@app.websocket("/ws/documents/{cid}")
async def doc_socket(ws: WebSocket, cid: int, access_token: str = "", name: str = "Guest"):
    """Presence and live pushes for one document. With sign-in on, the access token (session, API token or OIDC) is required."""
    from app import collab

    who = name[:40]
    if auth.mode() == "on":
        u = await run_in_threadpool(auth.identify, access_token)
        if not u:
            await ws.close(code=4401)
            return
        who = u.get("name") or u["email"]
    await collab.room(ws, cid, who)


@app.get("/api/ops/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    """Prometheus text format (admin only): counts and ages an operator alerts on."""
    with SessionLocal() as s:
        q = lambda sql: s.execute(text(sql)).scalar() or 0  # noqa: E731
        g = {"contractiq_contracts": q("SELECT count(*) FROM contracts WHERE status <> 'draft'"), "contractiq_drafts": q("SELECT count(*) FROM contracts WHERE status = 'draft'"),
             "contractiq_alerts_open": q("SELECT count(*) FROM alerts WHERE status = 'open'"), "contractiq_approvals_pending": q("SELECT count(*) FROM approvals WHERE status = 'pending'"),
             "contractiq_open_comment_threads": q("SELECT count(*) FROM comment_threads WHERE status = 'open'"),
             "contractiq_pipeline_failed_last_run": q("SELECT COALESCE(failed, 0) FROM pipeline_runs ORDER BY id DESC LIMIT 1"),
             "contractiq_pipeline_last_run_age_seconds": int(q("SELECT EXTRACT(EPOCH FROM now() - max(finished_at)) FROM pipeline_runs")),
             "contractiq_llm_calls_total": q("SELECT count(*) FROM llm_calls"), "contractiq_connectors_in_error": q("SELECT count(*) FROM connectors WHERE last_status = 'error'")}
    return "".join(f"# TYPE {k} gauge\n{k} {v}\n" for k, v in g.items())


@app.get("/health")
def health() -> dict[str, str]:
    """Green only if the DB is reachable and pgvector is installed."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        vec = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()
    return {"status": "ok", "db": "ok", "pgvector": "ok" if vec else "missing"}
