"""Тесты AI Teacher: строгий JSON, repair, режимы EXPLAIN/QUESTION."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from services.ai_teacher import (
    AITeacher,
    AITeacherError,
    ExplanationPayload,
    QuestionPayload,
    RequestMode,
    TeacherContext,
    extract_json,
    render_prompt,
)
from services.llm_client import LLMRequestError

EXPLAIN_JSON = json.dumps(
    {
        "type": "explanation",
        "text": "Блочная модель описывает content, padding, border и margin.",
        "key_points": ["padding изнутри", "margin снаружи"],
    },
    ensure_ascii=False,
)
QUESTION_JSON = json.dumps(
    {
        "type": "question",
        "question": "Чем padding отличается от margin?",
        "expected_concepts": ["padding", "margin"],
        "difficulty": 2,
    },
    ensure_ascii=False,
)


class FakeClient:
    """Подменяет OpenRouterClient: отдаёт заранее заданные ответы."""

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    async def complete_json(self, messages, **kwargs) -> str:
        self.calls.append(messages)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def context(mode: RequestMode = RequestMode.EXPLAIN) -> TeacherContext:
    return TeacherContext(
        mode=mode,
        course_title="CSS",
        topic_title="CSS Box Model",
        topic_description="content, padding, border, margin",
        concepts=["padding", "margin", "box-sizing"],
        difficulty=2,
        user_level=0.4,
        weak_concepts=["margin"],
    )


# --- успешные режимы --------------------------------------------------------


async def test_explain_success() -> None:
    client = FakeClient([EXPLAIN_JSON])
    teacher = AITeacher(client)

    payload = await teacher.explain(context())

    assert isinstance(payload, ExplanationPayload)
    assert payload.text.startswith("Блочная модель")
    assert payload.key_points == ["padding изнутри", "margin снаружи"]
    assert len(client.calls) == 1


async def test_question_success() -> None:
    client = FakeClient([QUESTION_JSON])
    teacher = AITeacher(client)

    payload = await teacher.ask_question(context(RequestMode.QUESTION))

    assert isinstance(payload, QuestionPayload)
    assert payload.difficulty == 2
    assert payload.expected_concepts == ["padding", "margin"]
    assert len(client.calls) == 1


async def test_context_is_injected_into_prompts() -> None:
    client = FakeClient([EXPLAIN_JSON])
    teacher = AITeacher(client)

    await teacher.explain(context())

    system = client.calls[0][0]["content"]
    user = client.calls[0][-1]["content"]
    assert "CSS Box Model" in system
    assert "40%" in system  # уровень ученика
    assert "JSON" in system
    assert "CSS Box Model" in user
    assert "padding" in user
    assert "margin" in user  # слабая концепция
    assert "EXPLAIN" in system


# --- repair -----------------------------------------------------------------


async def test_invalid_json_then_successful_repair() -> None:
    client = FakeClient(["это не JSON", QUESTION_JSON])
    teacher = AITeacher(client)

    payload = await teacher.ask_question(context(RequestMode.QUESTION))

    assert isinstance(payload, QuestionPayload)
    assert len(client.calls) == 2
    repair_prompt = client.calls[1][-1]["content"]
    assert "это не JSON" in repair_prompt  # модели вернули её ответ
    assert "json" in repair_prompt.lower()


async def test_pydantic_validation_error_triggers_repair() -> None:
    incomplete = json.dumps({"type": "explanation"})  # нет обязательного text
    client = FakeClient([incomplete, EXPLAIN_JSON])
    teacher = AITeacher(client)

    payload = await teacher.explain(context())

    assert isinstance(payload, ExplanationPayload)
    assert len(client.calls) == 2
    assert "валидац" in client.calls[1][-1]["content"].lower()


async def test_wrong_type_triggers_repair() -> None:
    client = FakeClient([QUESTION_JSON, EXPLAIN_JSON])
    teacher = AITeacher(client)

    payload = await teacher.explain(context())

    assert isinstance(payload, ExplanationPayload)
    assert len(client.calls) == 2


async def test_repair_failure_raises_controlled_error() -> None:
    client = FakeClient(["мусор", "тоже мусор"])
    teacher = AITeacher(client)

    with pytest.raises(AITeacherError):
        await teacher.explain(context())

    assert len(client.calls) == 2  # ровно одна попытка repair, без бесконечности


async def test_llm_error_is_wrapped() -> None:
    client = FakeClient([LLMRequestError("timeout")])
    teacher = AITeacher(client)

    with pytest.raises(AITeacherError):
        await teacher.explain(context())


async def test_fenced_json_is_accepted_without_repair() -> None:
    fenced = "```json\n" + EXPLAIN_JSON + "\n```"
    client = FakeClient([fenced])
    teacher = AITeacher(client)

    payload = await teacher.explain(context())

    assert isinstance(payload, ExplanationPayload)
    assert len(client.calls) == 1


async def test_missing_prompt_file_raises(tmp_path) -> None:
    teacher = AITeacher(FakeClient([]), prompts_dir=tmp_path)
    with pytest.raises(AITeacherError):
        await teacher.explain(context())


# --- валидация схем напрямую ------------------------------------------------


def test_question_difficulty_bounds() -> None:
    with pytest.raises(ValidationError):
        QuestionPayload.model_validate(
            {"type": "question", "question": "q", "difficulty": 99}
        )


def test_explanation_requires_non_empty_text() -> None:
    with pytest.raises(ValidationError):
        ExplanationPayload.model_validate({"type": "explanation", "text": ""})


def test_payload_type_is_strict() -> None:
    with pytest.raises(ValidationError):
        ExplanationPayload.model_validate({"type": "question", "text": "x"})


def test_render_prompt_keeps_json_braces() -> None:
    template = '{"type": "explanation", "text": "{{topic}}"}'
    assert render_prompt(template, {"topic": "Box Model"}) == (
        '{"type": "explanation", "text": "Box Model"}'
    )


def test_extract_json_strips_fences_and_prose() -> None:
    assert extract_json("```json\n{\"a\": 1}\n```") == '{"a": 1}'
    assert extract_json('Вот ответ: {"a": 1} — готово') == '{"a": 1}'
    assert extract_json("без json") == "без json"
