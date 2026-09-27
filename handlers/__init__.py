"""Регистрация всех роутеров бота."""

from __future__ import annotations

from aiogram import Dispatcher

from handlers import common, courses, progress


def register_routers(dp: Dispatcher) -> None:
    """Подключить роутеры к диспетчеру.

    Порядок важен: конкретные команды/кнопки идут до ``common`` с его
    catch-all обработчиком текста.
    """
    dp.include_router(courses.router)
    dp.include_router(progress.router)
    dp.include_router(common.router)
