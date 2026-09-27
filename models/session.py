"""Учебные сессии и очередь вопросов сессии."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, utcnow
from models.enums import SessionMode, SessionPhase, SessionStatus

if TYPE_CHECKING:
    from models.answer import Answer
    from models.course import Topic
    from models.question import Question
    from models.user import User


class StudySession(Base):
    __tablename__ = "study_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, nullable=False
    )

    mode: Mapped[SessionMode] = mapped_column(
        Enum(SessionMode, native_enum=False, length=16, validate_strings=True),
        default=SessionMode.LEARN,
        nullable=False,
    )
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, native_enum=False, length=16, validate_strings=True),
        default=SessionStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    phase: Mapped[SessionPhase] = mapped_column(
        Enum(SessionPhase, native_enum=False, length=16, validate_strings=True),
        default=SessionPhase.EXPLANATION,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[float | None] = mapped_column(Float)
    total_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    current_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("session_items.id", ondelete="SET NULL")
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    topic: Mapped["Topic"] = relationship()
    items: Mapped[list["SessionItem"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="SessionItem.order_index",
        foreign_keys="SessionItem.session_id",
    )
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class SessionItem(Base):
    """Один вопрос в очереди сессии/экзамена (нужен для восстановления сессии)."""

    __tablename__ = "session_items"
    __table_args__ = (
        UniqueConstraint("session_id", "order_index", name="uq_item_session_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    answered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    score: Mapped[float | None] = mapped_column(Float)

    session: Mapped["StudySession"] = relationship(
        back_populates="items", foreign_keys=[session_id]
    )
    question: Mapped["Question"] = relationship()
