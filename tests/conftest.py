"""Общие фикстуры для тестов."""

from __future__ import annotations

import pytest
import pytest_asyncio

from config import Config
from database import Database


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Убрать все переменные окружения, влияющие на Config."""
    for name in (
        "TELEGRAM_BOT_TOKEN",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "OPENROUTER_BASE_URL",
        "OPENROUTER_APP_NAME",
        "DB_PATH",
        "COURSES_DIR",
        "LOG_LEVEL",
        "AI_TIMEOUT_SECONDS",
        "AI_MAX_RETRIES",
        "DEFAULT_REMINDER_INTERVAL_MINUTES",
        "REMINDER_MIN_INTERVAL_MINUTES",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def config(tmp_path) -> Config:
    """Конфиг для тестов: без реальных секретов, БД в tmp."""
    return Config(
        bot_token="123456:TEST-TOKEN",
        openrouter_api_key="sk-or-test",
        db_path=tmp_path / "test.db",
    )


@pytest_asyncio.fixture
async def db(tmp_path) -> Database:
    """Инициализированная временная SQLite-БД."""
    database = Database(tmp_path / "test.db")
    await database.init()
    try:
        yield database
    finally:
        await database.dispose()
