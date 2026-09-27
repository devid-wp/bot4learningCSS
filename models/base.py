"""Базовые классы и утилиты SQLAlchemy-моделей."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Текущее время в UTC (все timestamps храним в UTC)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Единая декларативная база проекта."""

    def __repr__(self) -> str:  # pragma: no cover - удобство отладки
        pk = getattr(self, "id", "?")
        return f"<{type(self).__name__} id={pk}>"


class TimestampMixin:
    """Добавляет ``created_at``. Накладывается на модели верхнего уровня."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
