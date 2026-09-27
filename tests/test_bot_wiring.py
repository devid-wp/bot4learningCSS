"""Проверка сборки диспетчера и клавиатуры (без сети)."""

from __future__ import annotations

from bot import BOT_COMMANDS, build_dispatcher
from keyboards.main import (
    BTN_EXAM,
    BTN_LEARN,
    BTN_PROGRESS,
    BTN_SETTINGS,
    BTN_STATS,
    main_menu,
)


def test_dispatcher_builds() -> None:
    dp = build_dispatcher()
    assert dp is not None
    # роутер common подключён
    assert any(r.name == "common" for r in dp.sub_routers)


def test_missing_token_returns_cleanly(clean_env: None) -> None:  # noqa: F811
    # Bot не создаётся без токена: main() должен вернуться без исключения.
    import asyncio

    from bot import main

    asyncio.run(main())  # не должно бросить


def test_main_menu_buttons() -> None:
    kb = main_menu()
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert {BTN_LEARN, BTN_PROGRESS, BTN_EXAM, BTN_STATS, BTN_SETTINGS} <= labels


def test_command_list_complete() -> None:
    names = {c for c, _ in BOT_COMMANDS}
    assert {
        "start",
        "courses",
        "learn",
        "progress",
        "stats",
        "exam",
        "stop",
        "help",
    } <= names
