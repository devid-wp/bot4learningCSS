"""Тесты логики прогресса (services/progress_service)."""

from __future__ import annotations

from database import Database
from models import Course, ProgressStatus, Topic, User, UserProgress
from models.base import utcnow
from services.progress_service import format_course_progress, get_course_progress


async def _setup(db: Database):
    async with db.session() as session:
        course = Course(slug="css", name="CSS")
        session.add(course)
        await session.flush()
        first = Topic(course_id=course.id, slug="selectors", name="Selectors", order_index=1)
        second = Topic(course_id=course.id, slug="box_model", name="Box Model", order_index=2)
        session.add_all([first, second])
        user = User(telegram_id=1)
        session.add(user)
        await session.flush()
        return course.id, first.id, second.id, user.id


async def test_progress_without_rows_is_all_not_started(db: Database) -> None:
    course_id, first_id, _, user_id = await _setup(db)

    async with db.session() as session:
        course = await session.get(Course, course_id)
        progress = await get_course_progress(session, user_id=user_id, course=course)

    assert progress.total == 2
    assert (progress.mastered, progress.in_progress, progress.not_started) == (0, 0, 2)
    assert progress.current_topic is not None
    assert progress.current_topic.id == first_id
    assert all(item.status is ProgressStatus.NOT_STARTED for item in progress.topics)


async def test_progress_counts_and_current_topic(db: Database) -> None:
    course_id, first_id, second_id, user_id = await _setup(db)

    async with db.session() as session:
        session.add(
            UserProgress(
                user_id=user_id,
                topic_id=first_id,
                status=ProgressStatus.MASTERED,
                mastery=0.9,
                attempts=4,
                correct_answers=4,
                last_score=0.95,
                last_studied_at=utcnow(),
            )
        )
        session.add(
            UserProgress(
                user_id=user_id,
                topic_id=second_id,
                status=ProgressStatus.LEARNING,
                mastery=0.4,
                attempts=1,
                last_studied_at=utcnow(),
            )
        )

    async with db.session() as session:
        course = await session.get(Course, course_id)
        progress = await get_course_progress(session, user_id=user_id, course=course)

    assert (progress.mastered, progress.in_progress, progress.not_started) == (1, 1, 0)
    assert progress.percent == 50
    # активная тема приоритетнее не начатой
    assert progress.current_topic.id == second_id


async def test_all_mastered_has_no_current_topic(db: Database) -> None:
    course_id, first_id, second_id, user_id = await _setup(db)

    async with db.session() as session:
        for topic_id in (first_id, second_id):
            session.add(
                UserProgress(
                    user_id=user_id,
                    topic_id=topic_id,
                    status=ProgressStatus.MASTERED,
                    mastery=0.9,
                    attempts=3,
                )
            )

    async with db.session() as session:
        course = await session.get(Course, course_id)
        progress = await get_course_progress(session, user_id=user_id, course=course)

    assert progress.current_topic is None
    assert progress.mastered == 2
    assert "всё освоено" in format_course_progress(progress)


async def test_format_does_not_invent_mastery(db: Database) -> None:
    course_id, _, _, user_id = await _setup(db)

    async with db.session() as session:
        course = await session.get(Course, course_id)
        progress = await get_course_progress(session, user_id=user_id, course=course)
        text = format_course_progress(progress)

    # у тем без попыток не должно быть процентов мастерства
    assert "%" not in text.split("Темы")[1]
    assert "Не начато: 2" in text
