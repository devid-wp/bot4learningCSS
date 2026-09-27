"""Ответы пользователя и результат их проверки AI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin
from models.enums import AnswerResult

if TYPE_CHECKING:
    from models.question import Question
    from models.session import StudySession


class Answer(Base, TimestampMixin):
    __tablename__ = "answers"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )

    user_answer: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    result: Mapped[AnswerResult] = mapped_column(
        Enum(AnswerResult, native_enum=False, length=24, validate_strings=True),
        nullable=False,
    )
    feedback: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    mastered_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    weak_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    session: Mapped["StudySession"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship()
