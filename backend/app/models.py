"""ORM models. The schema itself is owned by Alembic migrations (see alembic/versions)."""

from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ARRAY, BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


class Template(Base):
    __tablename__ = "templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    type: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text, default="1.0")
    body_md: Mapped[str] = mapped_column(Text)


class TemplateClause(Base):
    __tablename__ = "template_clauses"
    id: Mapped[int] = mapped_column(primary_key=True)
    template_id: Mapped[int] = mapped_column(ForeignKey("templates.id", ondelete="CASCADE"))
    clause_type: Mapped[str] = mapped_column(Text)
    standard_text: Mapped[str] = mapped_column(Text)
    playbook_position: Mapped[str | None] = mapped_column(Text)
    fallback_text: Mapped[str | None] = mapped_column(Text)
    severity_if_missing: Mapped[str] = mapped_column(Text, default="medium")


class Contract(Base):
    __tablename__ = "contracts"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text)
    vendor: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    template_id: Mapped[int | None] = mapped_column(ForeignKey("templates.id"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("contracts.id"))
    status: Mapped[str] = mapped_column(Text, default="active")
    source_url: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    notice_period_days: Mapped[int | None] = mapped_column(Integer)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    annual_value: Mapped[float | None] = mapped_column(Numeric(16, 2))
    total_value: Mapped[float | None] = mapped_column(Numeric(16, 2))
    currency: Mapped[str] = mapped_column(Text, default="USD")
    payment_terms_days: Mapped[int | None] = mapped_column(Integer)
    liability_cap_multiple: Mapped[float | None] = mapped_column(Numeric(6, 2))  # NULL = uncapped
    liability_cap_text: Mapped[str | None] = mapped_column(Text)
    termination_for_convenience: Mapped[bool | None] = mapped_column(Boolean)
    governing_law: Mapped[str | None] = mapped_column(Text)
    processes_personal_data: Mapped[bool] = mapped_column(Boolean, default=False)
    has_dpa: Mapped[bool] = mapped_column(Boolean, default=False)
    owner: Mapped[str | None] = mapped_column(Text)
    property: Mapped[str | None] = mapped_column(Text)
    # Amendments only: names of the contract columns this amendment overrides. Needed because
    # liability_cap_multiple NULL means "uncapped", so NULL can't also mean "not overridden".
    customer_signatory: Mapped[str | None] = mapped_column(Text)
    customer_signed_date: Mapped[date | None] = mapped_column(Date)
    supplier_signatory: Mapped[str | None] = mapped_column(Text)
    supplier_signed_date: Mapped[date | None] = mapped_column(Date)
    fully_executed: Mapped[bool] = mapped_column(Boolean, default=False)
    source_path: Mapped[str | None] = mapped_column(Text)
    source_size: Mapped[int | None] = mapped_column(BigInteger)
    source_mtime_ns: Mapped[int | None] = mapped_column(BigInteger)
    content_hash: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    origin: Mapped[str] = mapped_column(Text, default="seed")
    overrides: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    body_md: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Clause(Base):
    __tablename__ = "clauses"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    clause_type: Mapped[str] = mapped_column(Text)
    heading: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text)
    page: Mapped[int | None] = mapped_column(Integer)
    embedding = mapped_column(Vector(EMBEDDING_DIM))


class FieldExtraction(Base):
    __tablename__ = "field_extractions"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    field: Mapped[str] = mapped_column(Text)
    value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    source_clause_id: Mapped[int | None] = mapped_column(
        ForeignKey("clauses.id", ondelete="SET NULL")
    )
    source_page: Mapped[int | None] = mapped_column(Integer)
    corrected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class ClauseDeviation(Base):
    __tablename__ = "clause_deviations"
    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    template_clause_id: Mapped[int] = mapped_column(
        ForeignKey("template_clauses.id", ondelete="CASCADE")
    )
    deviation_summary: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)


class LlmCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(Text)
    prompt_hash: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AskCache(Base):
    __tablename__ = "ask_cache"
    question_key: Mapped[str] = mapped_column(Text, primary_key=True)
    question: Mapped[str] = mapped_column(Text)
    response: Mapped[dict] = mapped_column(JSONB)
    source: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
