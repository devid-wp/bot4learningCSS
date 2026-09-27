"""Прогресс пользователя по темам."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, utcnow
from models.enums import ProgressStatus

if TYPE_CHECKING:
    from models.course import Topic
    from models.user import User


class UserProgress(Base):
    __tablename__ = "user_progress"
    __table_args__ = (UniqueConstraint("user_id", "topic_id", name="uq_progress_user_topic"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, nullable=False
    )

    status: Mapped[ProgressStatus] = mapped_column(
        Enum(ProgressStatus, native_enum=False, length=32, validate_strings=True),
        default=ProgressStatus.NOT_STARTED,
        nullable=False,
    )
    mastery: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_score: Mapped[float | None] = mapped_column(Float)
    last_studied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="progress")
    topic: Mapped["Topic"] = relationship(back_populates="progress")
