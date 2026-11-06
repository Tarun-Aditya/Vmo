from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://vmo:vmo@localhost:5432/vmo"
    readonly_database_url: str = "postgresql+psycopg://vmo_readonly:vmo_readonly@localhost:5432/vmo"
    anthropic_api_key: str = ""
    model_extract: str = "claude-sonnet-5-5"
    model_ask: str = "claude-sonnet-5-5"
    model_redline: str = "claude-sonnet-5-5"
    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384  # must match the vector(N) column in migration 0001


settings = Settings()
