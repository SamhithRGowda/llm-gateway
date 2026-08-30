"""SQLAlchemy model for request_logs, per PLAN.md Section 4.

The table itself is created by app/db/migrations/init.sql (Phase 1's chosen
migration approach); this model is used only for typed inserts/queries via
SQLAlchemy, introduced in Phase 4 per PLAN.md's repo structure
("app/usage/models.py # SQLAlchemy models: RequestLog").
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    api_key_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    model_alias: Mapped[str | None] = mapped_column(String, nullable=True)
    provider_used: Mapped[str | None] = mapped_column(String, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)
    attempt_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_occurred: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
