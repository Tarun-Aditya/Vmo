from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.db import engine
from app.routes import router

app = FastAPI(title="ContractIQ API", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """Green only if the DB is reachable and pgvector is installed."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        vec = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar()
    return {"status": "ok", "db": "ok", "pgvector": "ok" if vec else "missing"}
