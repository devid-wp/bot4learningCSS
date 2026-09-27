"""Мастерство по отдельным концепциям темы (для повтора слабых мест)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, utcnow

if TYPE_CHECKING:
    from models.course import Topic
    from models.user import User


class ConceptMastery(Base):
    __tablename__ = "concept_mastery"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", "concept", name="uq_concept_user_topic_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    concept: Mapped[str] = mapped_column(String(96), nullable=False)

    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship()
    topic: Mapped["Topic"] = relationship()
