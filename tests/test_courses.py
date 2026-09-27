"""Тесты YAML-загрузчика курсов и идемпотентного сида."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from sqlalchemy import func, select

from database import Database
from models import Course, Topic
from services.course_loader import (
    CourseConfigError,
    load_course_file,
    load_courses_dir,
    seed_courses,
)

VALID_CSS = """
course:
  slug: css
  title: CSS
  description: Styles
  order: 2
topics:
  - slug: selectors
    title: Selectors
    order: 1
    difficulty: 1
    concepts: [selector, class]
  - slug: box_model
    title: Box Model
    order: 2
    difficulty: 2
    concepts: [padding, margin]
"""

VALID_HTML = """
course:
  slug: html
  title: HTML
  order: 1
topics:
  - slug: forms
    title: Forms
    order: 1
"""


def _write(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


# --- YAML loading -----------------------------------------------------------


def test_load_valid_file(tmp_path: Path) -> None:
    spec = load_course_file(_write(tmp_path, "css.yaml", VALID_CSS))
    assert spec.course.slug == "css"
    assert spec.course.title == "CSS"
    assert spec.course.order == 2
    assert [t.slug for t in spec.topics] == ["selectors", "box_model"]
    assert spec.topics[0].concepts == ["selector", "class"]
    assert spec.topics[1].difficulty == 2


def test_invalid_yaml_syntax(tmp_path: Path) -> None:
    with pytest.raises(CourseConfigError):
        load_course_file(_write(tmp_path, "bad.yaml", "course: [unclosed\n  topics:"))


def test_missing_required_field(tmp_path: Path) -> None:
    broken = "course:\n  slug: css\ntopics:\n  - order: 1\n"  # нет title темы
    with pytest.raises(CourseConfigError):
        load_course_file(_write(tmp_path, "bad.yaml", broken))


def test_empty_topics_rejected(tmp_path: Path) -> None:
    broken = "course:\n  slug: css\n  title: CSS\ntopics: []\n"
    with pytest.raises(CourseConfigError):
        load_course_file(_write(tmp_path, "bad.yaml", broken))


def test_invalid_slug_rejected(tmp_path: Path) -> None:
    broken = VALID_CSS.replace("slug: css", "slug: CSS Upper!")
    with pytest.raises(CourseConfigError):
        load_course_file(_write(tmp_path, "bad.yaml", broken))


def test_duplicate_topic_slugs_rejected(tmp_path: Path) -> None:
    broken = VALID_CSS.replace("slug: box_model", "slug: selectors")
    with pytest.raises(CourseConfigError):
        load_course_file(_write(tmp_path, "bad.yaml", broken))


def test_unknown_field_rejected(tmp_path: Path) -> None:
    broken = VALID_CSS + "  unexpected: true\n"
    with pytest.raises(CourseConfigError):
        load_course_file(_write(tmp_path, "bad.yaml", broken))


def test_non_dict_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(CourseConfigError):
        load_course_file(_write(tmp_path, "bad.yaml", "- just\n- a list\n"))


def test_load_dir_multiple_courses_sorted(tmp_path: Path) -> None:
    _write(tmp_path, "css.yaml", VALID_CSS)
    _write(tmp_path, "html.yaml", VALID_HTML)
    specs = load_courses_dir(tmp_path)
    assert [s.course.slug for s in specs] == ["html", "css"]  # по order: 1, 2


def test_duplicate_course_slug_across_files(tmp_path: Path) -> None:
    _write(tmp_path, "a.yaml", VALID_CSS)
    _write(tmp_path, "b.yaml", VALID_CSS)
    with pytest.raises(CourseConfigError):
        load_courses_dir(tmp_path)


def test_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(CourseConfigError):
        load_courses_dir(tmp_path / "nope")


def test_bundled_courses_are_valid() -> None:
    """Реальные courses/*.yaml в репозитории должны проходить валидацию."""
    specs = load_courses_dir(Path(__file__).resolve().parent.parent / "courses")
    slugs = {s.course.slug for s in specs}
    assert {"html", "css", "js"} <= slugs
    assert all(spec.topics for spec in specs)


# --- Idempotent seeding -----------------------------------------------------


async def test_seed_is_idempotent(db: Database, tmp_path: Path) -> None:
    _write(tmp_path, "css.yaml", VALID_CSS)

    first = await seed_courses(db, tmp_path)
    assert (first.courses_created, first.topics_created) == (1, 2)

    second = await seed_courses(db, tmp_path)
    assert (second.courses_created, second.topics_created) == (0, 0)
    assert (second.courses_updated, second.topics_updated) == (0, 0)

    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Course)) == 1
        assert await session.scalar(select(func.count()).select_from(Topic)) == 2


async def test_seed_updates_existing_in_place(db: Database, tmp_path: Path) -> None:
    path = _write(tmp_path, "css.yaml", VALID_CSS)
    await seed_courses(db, tmp_path)

    path.write_text(
        textwrap.dedent(VALID_CSS)
        .replace("title: CSS", "title: CSS Advanced")
        .replace("title: Selectors", "title: CSS Selectors"),
        encoding="utf-8",
    )
    result = await seed_courses(db, tmp_path)

    assert result.courses_created == 0
    assert result.courses_updated == 1
    assert result.topics_created == 0
    assert result.topics_updated == 1

    async with db.session() as session:
        course = (
            await session.execute(select(Course).where(Course.slug == "css"))
        ).scalar_one()
        assert course.name == "CSS Advanced"
        assert await session.scalar(select(func.count()).select_from(Topic)) == 2


async def test_seed_multiple_courses_and_topics(db: Database, tmp_path: Path) -> None:
    _write(tmp_path, "css.yaml", VALID_CSS)
    _write(tmp_path, "html.yaml", VALID_HTML)

    result = await seed_courses(db, tmp_path)
    assert result.courses_created == 2
    assert result.topics_created == 3

    async with db.session() as session:
        assert await session.scalar(select(func.count()).select_from(Topic)) == 3


async def test_seed_persists_concepts(db: Database, tmp_path: Path) -> None:
    _write(tmp_path, "css.yaml", VALID_CSS)
    await seed_courses(db, tmp_path)

    async with db.session() as session:
        topic = (
            await session.execute(select(Topic).where(Topic.slug == "box_model"))
        ).scalar_one()
        assert topic.concepts == ["padding", "margin"]
        assert topic.difficulty == 2
