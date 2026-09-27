"""Курсы и темы."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

if TYPE_CHECKING:
    from models.progress import UserProgress
    from models.question import Question


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    topics: Mapped[list["Topic"]] = relationship(
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Topic.order_index",
    )


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (UniqueConstraint("course_id", "slug", name="uq_topic_course_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Список концепций темы (по ним AI Teacher строит вопросы и оценивает).
    concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    course: Mapped["Course"] = relationship(back_populates="topics")
    questions: Mapped[list["Question"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    progress: Mapped[list["UserProgress"]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
