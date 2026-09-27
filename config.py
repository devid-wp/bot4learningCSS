"""Конфигурация приложения.

Единственный источник секретов — переменные окружения / файл ``.env``.
В коде нет и не должно быть хардкода токенов.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

# .env читается один раз при импорте; отсутствие файла — не ошибка.
load_dotenv(ENV_FILE)


class ConfigError(RuntimeError):
    """Некорректная или неполная конфигурация."""


def _get_str(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return default
    raw = raw.strip()
    return raw or default


def _get_int(name: str, default: int) -> int:
    raw = _get_str(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} должно быть целым числом, получено {raw!r}") from exc


@dataclass(frozen=True, slots=True)
class Config:
    """Иммутабельный снимок настроек приложения."""

    bot_token: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_app_name: str = "css-tutor-bot"
    db_path: Path = BASE_DIR / "data" / "bot.db"
    courses_dir: Path = BASE_DIR / "courses"
    log_level: str = "INFO"
    ai_timeout_seconds: int = 30
    ai_max_retries: int = 3
    default_reminder_interval_minutes: int = 60
    reminder_min_interval_minutes: int = 30

    @classmethod
    def from_env(cls, *, require_bot_token: bool = True) -> "Config":
        token = _get_str("TELEGRAM_BOT_TOKEN", "") or ""
        if require_bot_token and not token:
            raise ConfigError(
                "TELEGRAM_BOT_TOKEN не задан. Скопируй .env.example в .env и заполни его."
            )

        raw_db = _get_str("DB_PATH", str(BASE_DIR / "data" / "bot.db"))
        db_path = Path(raw_db or "data/bot.db").expanduser()
        if not db_path.is_absolute():
            db_path = BASE_DIR / db_path

        raw_courses = _get_str("COURSES_DIR", str(BASE_DIR / "courses"))
        courses_dir = Path(raw_courses or "courses").expanduser()
        if not courses_dir.is_absolute():
            courses_dir = BASE_DIR / courses_dir

        return cls(
            bot_token=token,
            openrouter_api_key=_get_str("OPENROUTER_API_KEY", "") or "",
            openrouter_model=_get_str("OPENROUTER_MODEL", "openai/gpt-4o-mini") or "",
            openrouter_base_url=_get_str(
                "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
            )
            or "",
            openrouter_app_name=_get_str("OPENROUTER_APP_NAME", "css-tutor-bot") or "",
            db_path=db_path,
            courses_dir=courses_dir,
            log_level=(_get_str("LOG_LEVEL", "INFO") or "INFO").upper(),
            ai_timeout_seconds=_get_int("AI_TIMEOUT_SECONDS", 30),
            ai_max_retries=_get_int("AI_MAX_RETRIES", 3),
            default_reminder_interval_minutes=_get_int(
                "DEFAULT_REMINDER_INTERVAL_MINUTES", 60
            ),
            reminder_min_interval_minutes=_get_int("REMINDER_MIN_INTERVAL_MINUTES", 30),
        )

    def with_db_path(self, path: str | Path) -> "Config":
        """Вернуть копию конфига с другим путём к БД (удобно для тестов)."""
        return replace(self, db_path=Path(path))
