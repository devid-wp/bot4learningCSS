"""Точка входа: запуск Telegram-бота в режиме long polling."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from config import Config, ConfigError
from database import Database
from handlers import register_routers
from services.course_loader import CourseConfigError, seed_courses
from utils.logging import setup_logging

log = logging.getLogger(__name__)

BOT_COMMANDS: tuple[tuple[str, str], ...] = (
    ("start", "Регистрация и главное меню"),
    ("courses", "Список курсов"),
    ("learn", "Продолжить обучение"),
    ("progress", "Прогресс по курсу"),
    ("stats", "Статистика обучения"),
    ("exam", "Экзамен по пройденным темам"),
    ("stop", "Остановить учебную сессию"),
    ("help", "Справка"),
)


async def _set_commands(bot: Bot) -> None:
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in BOT_COMMANDS])


def build_dispatcher(db: Database | None = None) -> Dispatcher:
    dp = Dispatcher()
    if db is not None:
        # aiogram прокидывает ключи workflow_data в хендлеры как kwargs (db=...).
        dp["db"] = db
    register_routers(dp)
    return dp


async def main(config: Config | None = None) -> None:
    if config is None:
        try:
            config = Config.from_env()
        except ConfigError as exc:
            # Лог ещё не настроен — пишем в stderr через logging по умолчанию.
            logging.basicConfig(level=logging.INFO)
            log.error("Ошибка конфигурации: %s", exc)
            return

    setup_logging(config.log_level)

    database = Database(config.db_path)
    await database.init()
    log.info("База данных готова: %s", database.path)

    try:
        result = await seed_courses(database, config.courses_dir)
        log.info("Курсы синхронизированы (%s)", result.summary())
    except CourseConfigError as exc:
        # Бот продолжает работать, но курсы не загружены — сообщаем явно.
        log.error("Ошибка загрузки курсов: %s", exc)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(database)

    try:
        await _set_commands(bot)
        log.info("Бот запущен. Ожидаю сообщения…")
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await database.dispose()
        log.info("Бот остановлен.")


def run() -> None:
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    run()
