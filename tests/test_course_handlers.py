"""Интеграционные тесты /courses, /progress и callback-навигации.

Тесты прогоняют реальный роутинг aiogram через ``Dispatcher.feed_update``,
подменяя только сетевую сессию бота (``bot.session``), поэтому проверяются
и фильтры, и callback_data, и текст ответов.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.methods import EditMessageText, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update
from aiogram.types import User as TgUser
from sqlalchemy import select

from bot import build_dispatcher
from database import Database
from handlers import common, courses, progress
from keyboards.main import BTN_PROGRESS
from models import Course, ProgressStatus, Topic, User, UserProgress
from services.user_service import get_or_create_user

TOKEN = "123456789:AAFakeTokenForTestsOnly_0123456789abcd"


def _dispatcher_for(db: Database):
    """Собрать свежий Dispatcher для теста.

    aiogram-роутеры — модульные синглтоны, поэтому перед повторной сборкой
    отцепляем их от предыдущего диспетчера (в продакшене Dispatcher один).
    """
    for module in (courses, progress, common):
        module.router._parent_router = None  # type: ignore[attr-defined]
    return build_dispatcher(db)


@pytest.fixture
def bot() -> Bot:
    instance = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    instance.session = AsyncMock()  # type: ignore[assignment]
    return instance


def _message(text: str | None, uid: int = 1) -> Message:
    return Message(
        message_id=10,
        date=datetime.now(UTC),
        chat=Chat(id=uid, type="private"),
        from_user=TgUser(id=uid, is_bot=False, first_name="Tester"),
        text=text,
    )


def _callback(data: str, uid: int = 1) -> CallbackQuery:
    return CallbackQuery(
        id="cb1",
        from_user=TgUser(id=uid, is_bot=False, first_name="Tester"),
        chat_instance="chat-instance",
        data=data,
        message=_message("previous", uid=uid),
    )


def _sent(bot: Bot, method_type):
    """Список исходящих методов указанного типа, отправленных ботом."""
    calls = []
    for call in bot.session.call_args_list:  # type: ignore[attr-defined]
        if call.args and len(call.args) >= 2:
            calls.append(call.args[1])
    return [m for m in calls if isinstance(m, method_type)]


def _button_datas(markup) -> list[str]:
    return [b.callback_data for row in markup.inline_keyboard for b in row]


async def _seed(db: Database, *, with_progress: bool = False) -> tuple[int, int]:
    """Создать курс CSS с двумя темами; опционально — прогресс по первой."""
    async with db.session() as session:
        course = Course(slug="css", name="CSS", description="Styles", order_index=2)
        session.add(course)
        await session.flush()

        selectors = Topic(
            course_id=course.id, slug="selectors", name="Selectors", order_index=1
        )
        box_model = Topic(
            course_id=course.id, slug="box_model", name="Box Model", order_index=2
        )
        session.add_all([selectors, box_model])
        await session.flush()

        if with_progress:
            user = await get_or_create_user(session, telegram_id=1)
            session.add(
                UserProgress(
                    user_id=user.id,
                    topic_id=selectors.id,
                    status=ProgressStatus.MASTERED,
                    mastery=0.9,
                    attempts=3,
                )
            )
        return course.id, selectors.id


async def test_courses_command_lists_courses(db: Database, bot: Bot) -> None:
    await _seed(db)
    dp = _dispatcher_for(db)

    await dp.feed_update(bot, Update(update_id=1, message=_message("/courses")))

    sends = _sent(bot, SendMessage)
    assert sends, "бот должен ответить сообщением"
    assert "Курсы" in sends[-1].text
    datas = _button_datas(sends[-1].reply_markup)
    assert len(datas) == 1
    assert datas[0].startswith("course:view:")


async def test_course_view_callback_shows_description_and_count(
    db: Database, bot: Bot
) -> None:
    course_id, _ = await _seed(db)
    dp = _dispatcher_for(db)

    await dp.feed_update(
        bot,
        Update(update_id=2, callback_query=_callback(f"course:view:{course_id}")),
    )

    edits = _sent(bot, EditMessageText)
    assert edits
    assert "CSS" in edits[-1].text
    assert "Styles" in edits[-1].text
    assert "Тем: <b>2</b>" in edits[-1].text
    datas = _button_datas(edits[-1].reply_markup)
    assert f"course:progress:{course_id}" in datas
    assert "course:list:0" in datas


async def test_progress_without_active_course_shows_picker(
    db: Database, bot: Bot
) -> None:
    await _seed(db)
    dp = _dispatcher_for(db)

    await dp.feed_update(bot, Update(update_id=3, message=_message("/progress")))

    sends = _sent(bot, SendMessage)
    assert sends
    assert "Выбери курс" in sends[-1].text
    datas = _button_datas(sends[-1].reply_markup)
    assert datas and datas[0].startswith("course:progress:")


async def test_progress_callback_sets_active_course_and_renders(
    db: Database, bot: Bot
) -> None:
    course_id, _ = await _seed(db, with_progress=True)
    dp = _dispatcher_for(db)

    await dp.feed_update(
        bot,
        Update(update_id=4, callback_query=_callback(f"course:progress:{course_id}")),
    )

    edits = _sent(bot, EditMessageText)
    assert edits
    text = edits[-1].text
    assert "Прогресс — CSS" in text
    assert "Текущая тема" in text
    assert "Освоено: 1 из 2" in text
    assert "Не начато: 1" in text

    async with db.session() as session:
        user = (await session.execute(select(User))).scalar_one()
        assert user.active_course_id == course_id


async def test_progress_button_from_reply_keyboard(db: Database, bot: Bot) -> None:
    await _seed(db)
    dp = _dispatcher_for(db)

    await dp.feed_update(bot, Update(update_id=5, message=_message(BTN_PROGRESS)))

    sends = _sent(bot, SendMessage)
    assert sends
    assert "Выбери курс" in sends[-1].text


async def test_switch_course_callback_returns_to_picker(db: Database, bot: Bot) -> None:
    await _seed(db)
    dp = _dispatcher_for(db)

    await dp.feed_update(
        bot, Update(update_id=6, callback_query=_callback("course:plist:0"))
    )

    edits = _sent(bot, EditMessageText)
    assert edits
    assert "Выбери курс" in edits[-1].text
    datas = _button_datas(edits[-1].reply_markup)
    assert datas and datas[0].startswith("course:progress:")


async def test_back_to_courses_list_callback(db: Database, bot: Bot) -> None:
    await _seed(db)
    dp = _dispatcher_for(db)

    await dp.feed_update(
        bot, Update(update_id=7, callback_query=_callback("course:list:0"))
    )

    edits = _sent(bot, EditMessageText)
    assert edits
    assert "Курсы" in edits[-1].text
    assert _button_datas(edits[-1].reply_markup)[0].startswith("course:view:")
