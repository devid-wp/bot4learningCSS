"""Команда /progress и показ прогресса по курсу."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, User as TelegramUser
from sqlalchemy.ext.asyncio import AsyncSession

from database import Database
from keyboards.courses import CourseCB, courses_list_kb, progress_view_kb
from keyboards.main import BTN_PROGRESS
from services.course_service import get_course, list_courses
from services.progress_service import format_course_progress, get_course_progress
from services.user_service import get_or_create_user

router = Router(name="progress")

TEXT_PICK_COURSE = "📊 <b>Прогресс</b>\n\nВыбери курс:"
TEXT_NO_COURSES = "Курсы пока не загружены."


async def _ensure_user(session: AsyncSession, tg_user: TelegramUser | None):
    if tg_user is None:
        return None
    return await get_or_create_user(
        session,
        telegram_id=tg_user.id,
        username=tg_user.username,
        first_name=tg_user.first_name,
    )


@router.message(Command("progress"))
@router.message(F.text == BTN_PROGRESS)
async def cmd_progress(message: Message, db: Database) -> None:
    async with db.session() as session:
        user = await _ensure_user(session, message.from_user)
        course = (
            await get_course(session, user.active_course_id)
            if user is not None and user.active_course_id is not None
            else None
        )

        if course is None:
            courses = await list_courses(session)
            if not courses:
                await message.answer(TEXT_NO_COURSES)
                return
            await message.answer(
                TEXT_PICK_COURSE, reply_markup=courses_list_kb(courses, action="progress")
            )
            return

        progress = await get_course_progress(session, user_id=user.id, course=course)
        text = format_course_progress(progress)

    await message.answer(text, reply_markup=progress_view_kb())


@router.callback_query(CourseCB.filter(F.action == "progress"))
async def on_course_progress(
    callback: CallbackQuery, callback_data: CourseCB, db: Database
) -> None:
    async with db.session() as session:
        user = await _ensure_user(session, callback.from_user)
        course = await get_course(session, callback_data.course_id)
        if user is None or course is None:
            await callback.answer("Курс не найден", show_alert=True)
            return

        user.active_course_id = course.id
        progress = await get_course_progress(session, user_id=user.id, course=course)
        text = format_course_progress(progress)

    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=progress_view_kb())
    await callback.answer()


@router.callback_query(CourseCB.filter(F.action == "plist"))
async def on_progress_course_list(
    callback: CallbackQuery, callback_data: CourseCB, db: Database
) -> None:
    async with db.session() as session:
        courses = await list_courses(session)

    if not courses:
        await callback.answer(TEXT_NO_COURSES, show_alert=True)
        return

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            TEXT_PICK_COURSE, reply_markup=courses_list_kb(courses, action="progress")
        )
    await callback.answer()
