"""Главное меню пользователя (reply-клавиатура)."""

from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BTN_LEARN = "📚 Учиться"
BTN_PROGRESS = "📊 Прогресс"
BTN_EXAM = "📝 Экзамен"
BTN_STATS = "📈 Статистика"
BTN_SETTINGS = "⚙️ Настройки"

MAIN_BUTTONS: tuple[str, ...] = (
    BTN_LEARN,
    BTN_PROGRESS,
    BTN_EXAM,
    BTN_STATS,
    BTN_SETTINGS,
)


def main_menu() -> ReplyKeyboardMarkup:
    """Построить главное меню: 2 колонки, аккуратные подписи."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_LEARN), KeyboardButton(text=BTN_PROGRESS)],
            [KeyboardButton(text=BTN_EXAM), KeyboardButton(text=BTN_STATS)],
            [KeyboardButton(text=BTN_SETTINGS)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выбери действие или напиши ответ…",
    )
