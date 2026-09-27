"""Перечисления предметной области.

Хранятся в БД как VARCHAR (native_enum=False) — SQLite-friendly и легко
расширяемо без миграций.
"""

from __future__ import annotations

from enum import StrEnum


class ProgressStatus(StrEnum):
    NOT_STARTED = "not_started"
    LEARNING = "learning"
    REVIEW = "review"
    MASTERED = "mastered"


class SessionMode(StrEnum):
    LEARN = "learn"
    REVIEW = "review"
    EXAM = "exam"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    FINISHED = "finished"
    ABORTED = "aborted"


class SessionPhase(StrEnum):
    EXPLANATION = "explanation"
    EXAMPLE = "example"
    QUESTION = "question"
    ANSWERING = "answering"
    PRACTICE = "practice"
    FEEDBACK = "feedback"
    FINISHED = "finished"


class QuestionKind(StrEnum):
    CONCEPT = "concept"
    PRACTICE = "practice"
    CHOICE = "choice"


class QuestionSource(StrEnum):
    SEED = "seed"
    AI = "ai"


class AnswerResult(StrEnum):
    CORRECT = "correct"
    PARTIALLY_CORRECT = "partially_correct"
    INCORRECT = "incorrect"
