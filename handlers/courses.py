"""Команда /courses и навигация по курсам (inline-кнопки)."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from database import Database
from keyboards.courses import CourseCB, course_detail_kb, courses_list_kb
from services.course_service import count_topics, get_course, list_courses

router = Router(name="courses")

TEXT_COURSES_HEADER = "📚 <b>Курсы</b>\n\nВыбери курс, чтобы посмотреть детали:"
TEXT_NO_COURSES = "Курсы пока не загружены."


@router.message(Command("courses"))
async def cmd_courses(message: Message, db: Database) -> None:
    async with db.session() as session:
        courses = await list_courses(session)

    if not courses:
        await message.answer(TEXT_NO_COURSES)
        return

    await message.answer(
        TEXT_COURSES_HEADER, reply_markup=courses_list_kb(courses, action="view")
    )


@router.callback_query(CourseCB.filter(F.action == "view"))
async def on_course_view(
    callback: CallbackQuery, callback_data: CourseCB, db: Database
) -> None:
    async with db.session() as session:
        course = await get_course(session, callback_data.course_id)
        if course is None:
            await callback.answer("Курс не найден", show_alert=True)
            return
        topics = await count_topics(session, course.id)
        name = course.name
        description = course.description or ""

    text = f"📘 <b>{name}</b>\n\n{description}\n\n📑 Тем: <b>{topics}</b>"

    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=course_detail_kb(course.id))
    await callback.answer()


@router.callback_query(CourseCB.filter(F.action == "list"))
async def on_courses_list(
    callback: CallbackQuery, callback_data: CourseCB, db: Database
) -> None:
    async with db.session() as session:
        courses = await list_courses(session)

    if not courses:
        await callback.answer(TEXT_NO_COURSES, show_alert=True)
        return

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            TEXT_COURSES_HEADER, reply_markup=courses_list_kb(courses, action="view")
        )
    await callback.answer()
