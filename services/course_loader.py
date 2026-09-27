"""Загрузка курсов из YAML и идемпотентный сид в БД.

Важно: этот модуль не знает ничего про Telegram. Он только читает,
валидирует и синхронизирует структуру курса с базой.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import Database
from models import Course, Topic

SLUG_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"


class CourseConfigError(RuntimeError):
    """YAML-файл курса отсутствует, повреждён или не проходит валидацию."""


class TopicSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(pattern=SLUG_PATTERN, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    description: str = ""
    order: int = Field(default=0, ge=0)
    difficulty: int = Field(default=1, ge=1, le=3)
    concepts: list[str] = Field(default_factory=list)


class CourseMeta(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    slug: str = Field(pattern=SLUG_PATTERN, max_length=64)
    title: str = Field(min_length=1, max_length=128)
    description: str = ""
    order: int = Field(default=0, ge=0)


class CourseSpec(BaseModel):
    """Валидированное содержимое одного ``courses/*.yaml``."""

    model_config = ConfigDict(extra="forbid")

    course: CourseMeta
    topics: list[TopicSpec] = Field(min_length=1)

    @field_validator("topics")
    @classmethod
    def _unique_topic_slugs(cls, topics: list[TopicSpec]) -> list[TopicSpec]:
        seen: set[str] = set()
        for topic in topics:
            if topic.slug in seen:
                raise ValueError(f"дубликат slug темы: {topic.slug!r}")
            seen.add(topic.slug)
        return topics


@dataclass
class SyncResult:
    """Сколько записей создано/обновлено при синхронизации."""

    courses_created: int = 0
    courses_updated: int = 0
    topics_created: int = 0
    topics_updated: int = 0

    def add(self, other: "SyncResult") -> None:
        self.courses_created += other.courses_created
        self.courses_updated += other.courses_updated
        self.topics_created += other.topics_created
        self.topics_updated += other.topics_updated

    @property
    def courses_total(self) -> int:
        return self.courses_created + self.courses_updated

    def summary(self) -> str:
        return (
            f"курсов: +{self.courses_created} / ~{self.courses_updated}, "
            f"тем: +{self.topics_created} / ~{self.topics_updated}"
        )


# ---------------------------------------------------------------------------
# Чтение и валидация YAML (без БД)
# ---------------------------------------------------------------------------


def load_course_file(path: str | Path) -> CourseSpec:
    """Прочитать и провалидировать один YAML-файл курса."""
    path = Path(path)
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CourseConfigError(f"{path.name}: не удалось прочитать файл: {exc}") from exc

    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise CourseConfigError(f"{path.name}: некорректный YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise CourseConfigError(f"{path.name}: ожидался словарь с ключами course/topics")

    try:
        return CourseSpec.model_validate(raw)
    except ValidationError as exc:
        raise CourseConfigError(f"{path.name}: невалидная структура курса:\n{exc}") from exc


def load_courses_dir(directory: str | Path) -> list[CourseSpec]:
    """Прочитать все ``*.yaml`` / ``*.yml`` из директории.

    Проверяет уникальность slug курсов и сортирует по ``order``.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise CourseConfigError(f"Директория курсов не найдена: {directory}")

    files = sorted({*directory.glob("*.yaml"), *directory.glob("*.yml")})

    specs: list[CourseSpec] = []
    seen: dict[str, str] = {}
    for file_path in files:
        spec = load_course_file(file_path)
        slug = spec.course.slug
        if slug in seen:
            raise CourseConfigError(
                f"дубликат slug курса {slug!r}: {seen[slug]} и {file_path.name}"
            )
        seen[slug] = file_path.name
        specs.append(spec)

    specs.sort(key=lambda s: (s.course.order, s.course.slug))
    return specs


# ---------------------------------------------------------------------------
# Синхронизация с БД (идемпотентная)
# ---------------------------------------------------------------------------


async def sync_course(session: AsyncSession, spec: CourseSpec) -> SyncResult:
    """Создать или обновить курс и его темы. Дубликатов не появляется."""
    result = SyncResult()

    course = (
        await session.execute(select(Course).where(Course.slug == spec.course.slug))
    ).scalar_one_or_none()

    if course is None:
        course = Course(
            slug=spec.course.slug,
            name=spec.course.title,
            description=spec.course.description,
            order_index=spec.course.order,
        )
        session.add(course)
        await session.flush()
        result.courses_created += 1
    else:
        if (
            course.name != spec.course.title
            or course.description != spec.course.description
            or course.order_index != spec.course.order
        ):
            course.name = spec.course.title
            course.description = spec.course.description
            course.order_index = spec.course.order
            result.courses_updated += 1

    existing_topics = {
        topic.slug: topic
        for topic in (
            await session.execute(select(Topic).where(Topic.course_id == course.id))
        ).scalars()
    }

    for topic_spec in spec.topics:
        current = existing_topics.get(topic_spec.slug)
        concepts = list(topic_spec.concepts)
        if current is None:
            session.add(
                Topic(
                    course_id=course.id,
                    slug=topic_spec.slug,
                    name=topic_spec.title,
                    description=topic_spec.description,
                    difficulty=topic_spec.difficulty,
                    order_index=topic_spec.order,
                    concepts=concepts,
                )
            )
            result.topics_created += 1
        elif (
            current.name != topic_spec.title
            or current.description != topic_spec.description
            or current.difficulty != topic_spec.difficulty
            or current.order_index != topic_spec.order
            or current.concepts != concepts
        ):
            current.name = topic_spec.title
            current.description = topic_spec.description
            current.difficulty = topic_spec.difficulty
            current.order_index = topic_spec.order
            current.concepts = concepts
            result.topics_updated += 1

    await session.flush()
    return result


async def sync_courses(session: AsyncSession, specs: list[CourseSpec]) -> SyncResult:
    total = SyncResult()
    for spec in specs:
        total.add(await sync_course(session, spec))
    return total


async def seed_courses(db: Database, directory: str | Path) -> SyncResult:
    """Прочитать директорию и синхронизировать её с БД в одной транзакции."""
    specs = load_courses_dir(directory)
    async with db.session() as session:
        return await sync_courses(session, specs)
