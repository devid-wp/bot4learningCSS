"""Тесты регистрации пользователя (idempotent upsert)."""

from __future__ import annotations

from sqlalchemy import func, select

from database import Database
from models import User
from services.user_service import get_or_create_user, get_user_by_telegram_id


async def test_create_then_find(db: Database) -> None:
    async with db.session() as session:
        created = await get_or_create_user(
            session, telegram_id=500, username="dev", first_name="Dev"
        )
        assert created.id is not None

    async with db.session() as session:
        found = await get_user_by_telegram_id(session, 500)
        assert found is not None
        assert found.username == "dev"
        assert found.last_seen_at is not None


async def test_repeated_start_does_not_duplicate(db: Database) -> None:
    async with db.session() as session:
        first = await get_or_create_user(session, telegram_id=777, username="a")
        first_id = first.id

    async with db.session() as session:
        second = await get_or_create_user(session, telegram_id=777, username="b")
        assert second.id == first_id
        assert second.username == "b"

    async with db.session() as session:
        total = await session.scalar(select(func.count()).select_from(User))
        assert total == 1


async def test_unknown_user_returns_none(db: Database) -> None:
    async with db.session() as session:
        assert await get_user_by_telegram_id(session, 123456) is None
