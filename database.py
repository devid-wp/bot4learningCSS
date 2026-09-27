"""Асинхронное подключение к SQLite и жизненный цикл сессий."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from models import Base


class Database:
    """Тонкая обёртка над async engine + session factory.

    Использование::

        db = Database(cfg.db_path)
        await db.init()
        async with db.session() as session:
            ...
        await db.dispose()
    """

    def __init__(self, path: str | Path, *, echo: bool = False) -> None:
        self.path = Path(path)
        url = f"sqlite+aiosqlite:///{self.path}"
        self.engine: AsyncEngine = create_async_engine(url, echo=echo)

        # SQLite по умолчанию не проверяет FOREIGN KEY — включаем.
        event.listens_for(self.engine.sync_engine, "connect")(self._enable_foreign_keys)

        self._session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @staticmethod
    def _enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def init(self) -> None:
        """Создать схему, если её ещё нет (идемпотентно)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Сессия с автоматическим commit/rollback."""
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self.engine.dispose()
