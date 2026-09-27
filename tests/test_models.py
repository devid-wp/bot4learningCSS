"""Тесты схемы БД: создание, ограничения, внешние ключи."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from database import Database
from models import Course, Topic, User, UserProgress


async def _make_course_topic(session, *, slug: str = "css") -> Topic:
    course = Course(slug=slug, name=slug.upper())
    session.add(course)
    await session.flush()
    topic = Topic(course_id=course.id, slug="box_model", name="Box Model", order_index=1)
    session.add(topic)
    await session.flush()
    return topic


async def test_create_all_and_roundtrip(db: Database) -> None:
    async with db.session() as session:
        user = User(telegram_id=111, username="neo", first_name="Neo")
        session.add(user)

    async with db.session() as session:
        stored = (await session.execute(select(User))).scalar_one()
        assert stored.id is not None
        assert stored.telegram_id == 111
        assert stored.display_name == "Neo"
        assert stored.reminders_enabled is True
        assert stored.reminder_interval_minutes == 60
        assert stored.created_at is not None


async def test_telegram_id_is_unique(db: Database) -> None:
    async with db.session() as session:
        session.add(User(telegram_id=1))

    with pytest.raises(IntegrityError):
        async with db.session() as session:
            session.add(User(telegram_id=1))


async def test_progress_unique_per_user_topic(db: Database) -> None:
    async with db.session() as session:
        user = User(telegram_id=2)
        session.add(user)
        topic = await _make_course_topic(session)
        session.add(UserProgress(user_id=user.id, topic_id=topic.id))

    with pytest.raises(IntegrityError):
        async with db.session() as session:
            session.add(UserProgress(user_id=user.id, topic_id=topic.id))


async def test_foreign_keys_enforced(db: Database) -> None:
    with pytest.raises(IntegrityError):
        async with db.session() as session:
            session.add(UserProgress(user_id=999, topic_id=999))


async def test_topic_unique_slug_within_course(db: Database) -> None:
    async with db.session() as session:
        course = Course(slug="js", name="JS")
        session.add(course)
        await session.flush()
        session.add(Topic(course_id=course.id, slug="dom", name="DOM"))
        await session.flush()

    with pytest.raises(IntegrityError):
        async with db.session() as session:
            session.add(Topic(course_id=course.id, slug="dom", name="DOM again"))


async def test_cascade_delete_topics(db: Database) -> None:
    async with db.session() as session:
        course = Course(slug="html", name="HTML")
        session.add(course)
        await session.flush()
        session.add(Topic(course_id=course.id, slug="forms", name="Forms"))
        await session.flush()
        await session.delete(course)

    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Topic)) == 0
