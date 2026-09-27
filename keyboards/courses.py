"""Inline-клавиатуры для курсов и прогресса."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from models import Course


class CourseCB(CallbackData, prefix="course"):
    """callback_data вида ``course:<action>:<course_id>``."""

    action: str
    course_id: int = 0


def courses_list_kb(courses: list[Course], *, action: str = "view") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"📘 {course.name} · {len(course.topics)} тем",
                callback_data=CourseCB(action=action, course_id=course.id).pack(),
            )
        ]
        for course in courses
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def course_detail_kb(course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Прогресс",
                    callback_data=CourseCB(action="progress", course_id=course_id).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ К курсам",
                    callback_data=CourseCB(action="list").pack(),
                )
            ],
        ]
    )


def progress_view_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Сменить курс",
                    callback_data=CourseCB(action="plist").pack(),
                )
            ]
        ]
    )
