"""Прогресс пользователя по курсу.

Читает только реальные данные из БД: отсутствие записи ``user_progress``
означает «тема не начата» (это не выдуманные данные, а корректная семантика).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Course, ProgressStatus, Topic, UserProgress

_STATUS_ICON = {
    ProgressStatus.MASTERED: "✅",
    ProgressStatus.LEARNING: "📖",
    ProgressStatus.REVIEW: "🔁",
    ProgressStatus.NOT_STARTED: "⬜",
}


@dataclass
class TopicStatus:
    topic: Topic
    status: ProgressStatus
    mastery: float
    attempts: int
    last_studied_at: datetime | None = None

    @property
    def icon(self) -> str:
        return _STATUS_ICON[self.status]


@dataclass
class CourseProgress:
    course: Course
    topics: list[TopicStatus]
    current_topic: Topic | None

    @property
    def total(self) -> int:
        return len(self.topics)

    @property
    def mastered(self) -> int:
        return sum(1 for t in self.topics if t.status is ProgressStatus.MASTERED)

    @property
    def in_progress(self) -> int:
        return sum(
            1
            for t in self.topics
            if t.status in (ProgressStatus.LEARNING, ProgressStatus.REVIEW)
        )

    @property
    def not_started(self) -> int:
        return sum(1 for t in self.topics if t.status is ProgressStatus.NOT_STARTED)

    @property
    def percent(self) -> int:
        if not self.topics:
            return 0
        return round(100 * self.mastered / self.total)


def _pick_current(items: list[TopicStatus]) -> Topic | None:
    """Текущая тема = последняя активная (learning/review), иначе первая не начатая."""
    active = [
        item
        for item in items
        if item.status in (ProgressStatus.LEARNING, ProgressStatus.REVIEW)
    ]
    if active:
        return max(
            active,
            key=lambda item: item.last_studied_at or datetime.min.replace(tzinfo=UTC),
        ).topic

    for item in items:
        if item.status is ProgressStatus.NOT_STARTED:
            return item.topic
    return None


async def get_course_progress(
    session: AsyncSession, *, user_id: int, course: Course
) -> CourseProgress:
    topics = list(
        (
            await session.execute(
                select(Topic)
                .where(Topic.course_id == course.id)
                .order_by(Topic.order_index, Topic.id)
            )
        )
        .scalars()
        .all()
    )

    topic_ids = [topic.id for topic in topics]
    rows: list[UserProgress] = []
    if topic_ids:
        rows = list(
            (
                await session.execute(
                    select(UserProgress).where(
                        UserProgress.user_id == user_id,
                        UserProgress.topic_id.in_(topic_ids),
                    )
                )
            )
            .scalars()
            .all()
        )

    by_topic = {row.topic_id: row for row in rows}
    items: list[TopicStatus] = []
    for topic in topics:
        row = by_topic.get(topic.id)
        items.append(
            TopicStatus(
                topic=topic,
                status=row.status if row else ProgressStatus.NOT_STARTED,
                mastery=row.mastery if row else 0.0,
                attempts=row.attempts if row else 0,
                last_studied_at=row.last_studied_at if row else None,
            )
        )

    return CourseProgress(course=course, topics=items, current_topic=_pick_current(items))


def format_course_progress(progress: CourseProgress) -> str:
    """HTML-текст для Telegram."""
    lines = [f"📊 <b>Прогресс — {progress.course.name}</b>", ""]

    if progress.current_topic is None:
        lines.append("Текущая тема: <b>всё освоено</b> 🎉")
    else:
        current = next(
            (item for item in progress.topics if item.topic.id == progress.current_topic.id),
            None,
        )
        if current is not None and current.attempts > 0:
            lines.append(
                f"Текущая тема: <b>{progress.current_topic.name}</b> "
                f"({round(current.mastery * 100)}%)"
            )
        else:
            lines.append(f"Текущая тема: <b>{progress.current_topic.name}</b>")

    lines += [
        "",
        f"✅ Освоено: {progress.mastered} из {progress.total} ({progress.percent}%)",
        f"📖 В процессе: {progress.in_progress}",
        f"⬜ Не начато: {progress.not_started}",
        "",
        "<b>Темы</b>",
    ]

    for item in progress.topics:
        suffix = f" — {round(item.mastery * 100)}%" if item.attempts > 0 else ""
        lines.append(f"{item.icon} {item.topic.name}{suffix}")

    return "\n".join(lines)
