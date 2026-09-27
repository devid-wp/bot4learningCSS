"""Регистрация и обновление пользователей."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import User
from models.base import utcnow


async def get_user_by_telegram_id(
    session: AsyncSession, telegram_id: int
) -> User | None:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one_or_none()


async def get_or_create_user(
    session: AsyncSession,
    *,
    telegram_id: int,
    username: str | None = None,
    first_name: str | None = None,
) -> User:
    """Найти пользователя или создать его. Идемпотентно.

    При повторном вызове актуализирует username/first_name и last_seen_at.
    """
    user = await get_user_by_telegram_id(session, telegram_id)

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_seen_at=utcnow(),
        )
        session.add(user)
        await session.flush()
        return user

    user.username = username
    user.first_name = first_name
    user.last_seen_at = utcnow()
    await session.flush()
    return user
