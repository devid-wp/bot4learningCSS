"""Пользователи."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from models.course import Course
    from models.progress import UserProgress
    from models.session import StudySession


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))

    active_course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL")
    )

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Напоминания
    reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reminder_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    next_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Геймификация
    streak_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_study_date: Mapped[date | None] = mapped_column(Date)

    active_course: Mapped["Course | None"] = relationship()
    progress: Mapped[list["UserProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["StudySession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        return self.first_name or self.username or f"id{self.telegram_id}"
