"""Базовые команды: /start, /help, /stop и обработка неизвестных сообщений."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from database import Database
from keyboards.main import (
    BTN_EXAM,
    BTN_LEARN,
    BTN_SETTINGS,
    BTN_STATS,
    main_menu,
)
from services.user_service import get_or_create_user

router = Router(name="common")

WELCOME = (
    "👋 <b>Привет!</b> Я твой личный AI-преподаватель по программированию.\n\n"
    "Я не даю готовых ответов — я объясняю, задаю вопросы и проверяю, "
    "что ты <b>действительно понял</b> тему. Прогресс сохраняется.\n\n"
    "Начать можно с курса <b>HTML / CSS / JS</b>."
)

HELP_TEXT = (
    "ℹ️ <b>Команды</b>\n\n"
    "/start — регистрация и главное меню\n"
    "/courses — список курсов\n"
    "/learn — продолжить обучение с текущей темы\n"
    "/progress — прогресс по курсу\n"
    "/stats — статистика обучения\n"
    "/exam — экзамен по пройденным темам\n"
    "/stop — остановить текущую учебную сессию\n"
    "/help — эта справка\n\n"
    "Во время обучения отвечай своими словами — так я пойму, где ты путаешься."
)

NOT_IMPLEMENTED = "🚧 Этот раздел появится на следующем этапе разработки."


@router.message(CommandStart())
async def cmd_start(message: Message, db: Database) -> None:
    tg_user = message.from_user
    if tg_user is not None:
        async with db.session() as session:
            await get_or_create_user(
                session,
                telegram_id=tg_user.id,
                username=tg_user.username,
                first_name=tg_user.first_name,
            )
    await message.answer(WELCOME, reply_markup=main_menu())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, reply_markup=main_menu())


@router.message(Command("stop"))
async def cmd_stop(message: Message) -> None:
    # Реальная остановка сессии появится вместе с учебным движком (Этап 5).
    await message.answer("⏹ Останавливать пока нечего. Начнём? → /learn")


@router.message(Command("learn", "stats", "exam"))
async def cmd_stub(message: Message) -> None:
    await message.answer(NOT_IMPLEMENTED, reply_markup=main_menu())


@router.message(F.text.in_({BTN_LEARN, BTN_EXAM, BTN_STATS, BTN_SETTINGS}))
async def stub_buttons(message: Message) -> None:
    await message.answer(NOT_IMPLEMENTED, reply_markup=main_menu())


@router.message(F.text)
async def unknown_text(message: Message) -> None:
    """Мягкий ответ на всё остальное, чтобы бот не молчал."""
    await message.answer(
        "Я пока не понял это сообщение. Используй меню ниже или /help.",
        reply_markup=main_menu(),
    )
