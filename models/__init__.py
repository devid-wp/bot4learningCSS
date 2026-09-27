"""SQLAlchemy-модели проекта.

Импорт этого пакета регистрирует все таблицы в ``Base.metadata``.
"""

from __future__ import annotations

from models.answer import Answer
from models.base import Base, TimestampMixin, utcnow
from models.concept import ConceptMastery
from models.course import Course, Topic
from models.enums import (
    AnswerResult,
    ProgressStatus,
    QuestionKind,
    QuestionSource,
    SessionMode,
    SessionPhase,
    SessionStatus,
)
from models.progress import UserProgress
from models.question import Question
from models.session import SessionItem, StudySession
from models.user import User

__all__ = [
    "Answer",
    "AnswerResult",
    "Base",
    "ConceptMastery",
    "Course",
    "ProgressStatus",
    "Question",
    "QuestionKind",
    "QuestionSource",
    "SessionItem",
    "SessionMode",
    "SessionPhase",
    "SessionStatus",
    "StudySession",
    "TimestampMixin",
    "Topic",
    "User",
    "UserProgress",
    "utcnow",
]
