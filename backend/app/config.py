from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vmo:vmo@localhost:5432/vmo"
    readonly_database_url: str = "postgresql+psycopg://vmo_readonly:vmo_readonly@localhost:5432/vmo"
    anthropic_api_key: str = ""
    model_extract: str = "claude-sonnet-5-5"
    customer_names: str = "Arcadia"   # comma-separated: how our own company is named in contracts
    llm_provider: str = "auto"  # auto | api | claude_code | offline
    model_ask: str = "claude-sonnet-5-5"
    model_redline: str = "claude-sonnet-5-5"
    embedding_provider: str = "auto"  # auto | local (sentence-transformers) | hash (offline)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    data_dir: str = "/data"
    embedding_dim: int = 384  # must match the vector(N) column in migration 0001


settings = Settings()


def data_path():
    """Docker mounts ./data at /data; fall back to the repo's ./data when run on the host."""
    from pathlib import Path

    p = Path(settings.data_dir)
    return p if p.exists() else Path(__file__).resolve().parents[2] / "data"
