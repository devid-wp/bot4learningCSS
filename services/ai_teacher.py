"""AI Teacher: превращает структурированный контекст в строгий JSON.

На этом этапе поддерживаются два режима:

- ``EXPLAIN``  — краткое объяснение темы;
- ``QUESTION`` — один проверочный вопрос по теме.

Модуль не знает про Telegram и БД: он получает контекст и возвращает
валидированные Pydantic-модели. Если модель вернула невалидный JSON —
делается ровно одна попытка repair. Если и она не удалась, поднимается
контролируемая ``AITeacherError`` (никакого мусора и падений хендлера).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from services.llm_client import LLMError

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

SYSTEM_PROMPT_FILE = "system_teacher.md"
REPAIR_PROMPT_FILE = "repair.md"


class RequestMode(StrEnum):
    EXPLAIN = "EXPLAIN"
    QUESTION = "QUESTION"


class AITeacherError(RuntimeError):
    """Контролируемая ошибка AI Teacher (невалидный JSON, ошибка LLM и т.п.)."""


class LLMClient(Protocol):
    """Минимальный интерфейс клиента, нужный AI Teacher."""

    async def complete_json(
        self, messages: list[dict[str, str]], **kwargs: Any
    ) -> str: ...


# ---------------------------------------------------------------------------
# Схемы ответов
# ---------------------------------------------------------------------------


class ExplanationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: Literal["explanation"]
    text: str = Field(min_length=1)
    key_points: list[str] = Field(default_factory=list)


class QuestionPayload(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    type: Literal["question"]
    question: str = Field(min_length=1)
    expected_concepts: list[str] = Field(default_factory=list)
    difficulty: int = Field(default=1, ge=1, le=3)


# ---------------------------------------------------------------------------
# Контекст
# ---------------------------------------------------------------------------


@dataclass
class TeacherContext:
    """Структурированный контекст для одного запроса к AI."""

    mode: RequestMode
    course_title: str
    topic_title: str
    topic_description: str = ""
    concepts: list[str] = field(default_factory=list)
    difficulty: int = 1
    user_level: float = 0.0
    weak_concepts: list[str] = field(default_factory=list)

    def as_prompt_values(self) -> dict[str, str]:
        level = max(0.0, min(1.0, self.user_level))
        return {
            "mode": self.mode.value,
            "course": self.course_title,
            "topic": self.topic_title,
            "topic_description": self.topic_description or "—",
            "concepts": ", ".join(self.concepts) or "—",
            "difficulty": str(self.difficulty),
            "user_level": f"{round(level * 100)}%",
            "weak_concepts": ", ".join(self.weak_concepts) or "нет",
        }


# ---------------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------------


def render_prompt(template: str, values: dict[str, str]) -> str:
    """Подставить ``{{ключ}}`` без риска сломаться на JSON-фигурных скобках."""
    result = template
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*")


def extract_json(raw: str) -> str:
    """Достать JSON из ответа модели (снимает ```-обёртки и текст вокруг)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = _FENCE_RE.sub("", text)
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]
    return text


# ---------------------------------------------------------------------------
# AI Teacher
# ---------------------------------------------------------------------------


class AITeacher:
    def __init__(
        self,
        client: LLMClient,
        *,
        prompts_dir: str | Path | None = None,
        temperature: float = 0.4,
    ) -> None:
        self._client = client
        self._prompts_dir = Path(prompts_dir) if prompts_dir is not None else PROMPTS_DIR
        self._temperature = temperature
        self._prompt_cache: dict[str, str] = {}

    # -- публичные режимы ---------------------------------------------------

    async def explain(self, context: TeacherContext) -> ExplanationPayload:
        context = replace(context, mode=RequestMode.EXPLAIN)
        payload = await self._generate(context, ExplanationPayload, "explain.md")
        return payload  # type: ignore[return-value]

    async def ask_question(self, context: TeacherContext) -> QuestionPayload:
        context = replace(context, mode=RequestMode.QUESTION)
        payload = await self._generate(context, QuestionPayload, "question.md")
        return payload  # type: ignore[return-value]

    # -- внутренняя механика ------------------------------------------------

    async def _generate(
        self, context: TeacherContext, schema: type[BaseModel], template_name: str
    ) -> BaseModel:
        values = context.as_prompt_values()
        system = render_prompt(self._load_prompt(SYSTEM_PROMPT_FILE), values)
        user = render_prompt(self._load_prompt(template_name), values)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        raw = await self._call(messages)
        payload, error = self._parse(raw, schema)
        if payload is not None:
            return payload

        log.warning("AI вернула невалидный ответ (%s) — запускаю repair", error)
        repair_messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": self._repair_prompt(context, schema, raw, error)},
        ]
        repaired = await self._call(repair_messages)
        payload, error = self._parse(repaired, schema)
        if payload is not None:
            return payload

        log.error("Repair не помог: %s", error)
        raise AITeacherError("не удалось получить валидный JSON от AI после repair")

    async def _call(self, messages: list[dict[str, str]]) -> str:
        try:
            return await self._client.complete_json(messages)
        except LLMError as exc:
            raise AITeacherError(f"ошибка LLM: {exc}") from exc

    def _repair_prompt(
        self,
        context: TeacherContext,
        schema: type[BaseModel],
        raw: str,
        error: str,
    ) -> str:
        values = context.as_prompt_values()
        values["raw_response"] = raw
        values["validation_error"] = error
        values["json_schema"] = json.dumps(
            schema.model_json_schema(), ensure_ascii=False, indent=2
        )
        return render_prompt(self._load_prompt(REPAIR_PROMPT_FILE), values)

    @staticmethod
    def _parse(raw: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str]:
        try:
            data = json.loads(extract_json(raw))
        except (ValueError, TypeError) as exc:
            return None, f"некорректный JSON: {exc}"

        try:
            return schema.model_validate(data), ""
        except ValidationError as exc:
            return None, f"ответ не прошёл валидацию: {exc}"

    def _load_prompt(self, name: str) -> str:
        if name not in self._prompt_cache:
            path = self._prompts_dir / name
            try:
                self._prompt_cache[name] = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise AITeacherError(f"не найден prompt '{name}': {exc}") from exc
        return self._prompt_cache[name]
