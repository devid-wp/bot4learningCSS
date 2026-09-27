"""Вопросы (заготовки и сгенерированные AI)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin
from models.enums import QuestionKind, QuestionSource

if TYPE_CHECKING:
    from models.course import Topic


class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, nullable=False
    )

    text: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[QuestionKind] = mapped_column(
        Enum(QuestionKind, native_enum=False, length=16, validate_strings=True),
        default=QuestionKind.CONCEPT,
        nullable=False,
    )
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    options: Mapped[list[str] | None] = mapped_column(JSON)
    reference_answer: Mapped[str | None] = mapped_column(Text)
    source: Mapped[QuestionSource] = mapped_column(
        Enum(QuestionSource, native_enum=False, length=16, validate_strings=True),
        default=QuestionSource.AI,
        nullable=False,
    )
    hint: Mapped[str | None] = mapped_column(Text)

    topic: Mapped["Topic"] = relationship(back_populates="questions")
