"""Запросы к курсам и темам (тонкий слой над ORM)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Course, Topic


async def list_courses(session: AsyncSession) -> list[Course]:
    """Все курсы с предзагруженными темами, по порядку."""
    result = await session.execute(
        select(Course)
        .options(selectinload(Course.topics))
        .order_by(Course.order_index, Course.name)
    )
    return list(result.scalars().all())


async def get_course(session: AsyncSession, course_id: int) -> Course | None:
    return await session.get(Course, course_id)


async def count_topics(session: AsyncSession, course_id: int) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(Topic).where(Topic.course_id == course_id)
        )
        or 0
    )
