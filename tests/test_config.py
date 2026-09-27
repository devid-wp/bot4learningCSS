"""Тесты конфигурации."""

from __future__ import annotations

import pytest

from config import BASE_DIR, Config, ConfigError
from tests.conftest import clean_env  # noqa: F401  (фикстура)


def test_missing_token_raises(clean_env: None) -> None:
    with pytest.raises(ConfigError):
        Config.from_env()


def test_token_not_required_for_tests(clean_env: None) -> None:
    cfg = Config.from_env(require_bot_token=False)
    assert cfg.bot_token == ""
    assert cfg.openrouter_model == "openai/gpt-4o-mini"
    assert cfg.openrouter_base_url == "https://openrouter.ai/api/v1"
    assert cfg.log_level == "INFO"


def test_values_from_env(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("AI_MAX_RETRIES", "5")
    monkeypatch.setenv("DB_PATH", "data/custom.db")

    cfg = Config.from_env()
    assert cfg.bot_token == "123:abc"
    assert cfg.openrouter_model == "anthropic/claude-3.5-sonnet"
    assert cfg.log_level == "DEBUG"
    assert cfg.ai_max_retries == 5
    assert cfg.db_path == BASE_DIR / "data" / "custom.db"


def test_invalid_int_raises(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_TIMEOUT_SECONDS", "not-a-number")
    with pytest.raises(ConfigError):
        Config.from_env(require_bot_token=False)


def test_absolute_db_path_kept(clean_env: None, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    target = tmp_path / "abs.db"
    monkeypatch.setenv("DB_PATH", str(target))
    cfg = Config.from_env(require_bot_token=False)
    assert cfg.db_path == target


def test_with_db_path(config: Config, tmp_path) -> None:
    other = tmp_path / "other.db"
    assert config.with_db_path(other).db_path == other
    # исходный конфиг не изменён (frozen)
    assert config.db_path != other
