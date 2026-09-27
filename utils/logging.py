"""Настройка логирования с редакцией секретов.

Никогда не логируем токены и API-ключи. Фильтр маскирует их даже если
они случайно попали в текст сообщения лога.
"""

from __future__ import annotations

import logging
import re

# Паттерны секретов, которые нужно вырезать из логов.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # OpenRouter / OpenAI-подобные ключи
    re.compile(r"sk-or-[A-Za-z0-9._\-]+"),
    re.compile(r"sk-[A-Za-z0-9._\-]{16,}"),
    # Токен Telegram-бота: <digits>:<base64ish>
    re.compile(r"\b\d{6,12}:[A-Za-z0-9_\-]{30,}\b"),
)

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """Заменить все секреты в строке на заглушку."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


class SecretRedactingFilter(logging.Filter):
    """Фильтр, который вычищает секреты из сообщений перед выводом."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - защита от кривого форматирования
            return True

        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


def setup_logging(level: str = "INFO") -> None:
    """Сконфигурировать корневой логгер приложения."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    handler.addFilter(SecretRedactingFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # aiogram/aiohttp шумят на INFO — приглушаем.
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
