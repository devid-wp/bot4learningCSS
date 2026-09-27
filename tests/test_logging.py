"""Тесты редакции секретов в логах."""

from __future__ import annotations

import logging

from utils.logging import SecretRedactingFilter, redact


def test_redact_openrouter_key() -> None:
    assert redact("key=sk-or-v1-abcdef123456") == "key=***REDACTED***"


def test_redact_telegram_token() -> None:
    text = "token 123456789:AAF-verysecrettokenvalue1234567890 here"
    assert "AAF-verysecret" not in redact(text)


def test_redact_leaves_normal_text() -> None:
    assert redact("обычный текст про padding") == "обычный текст про padding"


def test_filter_rewrites_record() -> None:
    record = logging.LogRecord(
        name="t",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="api key %s",
        args=("sk-or-v1-secretsecret",),
        exc_info=None,
    )
    SecretRedactingFilter().filter(record)
    assert "sk-or-v1-secretsecret" not in record.getMessage()
