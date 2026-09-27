"""Асинхронный клиент OpenRouter (OpenAI-compatible).

Изолирует всю работу с сетью и ошибками API:
- timeout;
- ограниченный retry с экспоненциальным backoff;
- обработка rate limit (429) с учётом ``Retry-After``;
- обработка 5xx (retry) и прочих ошибок;
- fallback, если модель не поддерживает ``response_format=json_object``.

Секреты не логируются: заголовок Authorization никогда не пишется в лог,
а тело ответа прогоняется через ``redact``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx

from utils.logging import redact

log = logging.getLogger(__name__)

BACKOFF_BASE_SECONDS = 0.8
BACKOFF_MAX_SECONDS = 8.0
RETRY_AFTER_MAX_SECONDS = 30.0
BODY_PREVIEW_LIMIT = 300


class LLMError(RuntimeError):
    """Базовая ошибка клиента LLM."""


class LLMConfigError(LLMError):
    """Некорректная конфигурация (например, нет API-ключа)."""


class LLMRequestError(LLMError):
    """Сетевая ошибка или таймаут."""


class LLMRateLimitError(LLMError):
    """Превышен rate limit (HTTP 429)."""

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class LLMAPIError(LLMError):
    """OpenRouter вернул ошибку API."""

    def __init__(
        self, message: str, *, status_code: int | None = None, body: str = ""
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


# ---------------------------------------------------------------------------
# Разбор ответа
# ---------------------------------------------------------------------------


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= BODY_PREVIEW_LIMIT:
        return text
    return text[:BODY_PREVIEW_LIMIT] + "…"


def _safe_body(response: httpx.Response) -> str:
    """Тело ответа, безопасное для логирования (без секретов, короткое)."""
    try:
        raw = response.text
    except Exception:  # pragma: no cover - защита
        return ""
    return redact(_truncate(raw))


def _parse_retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _mentions_json_mode(body: str) -> bool:
    text = (body or "").lower()
    return "response_format" in text or "json_object" in text


def _extract_content(data: Any) -> str:
    choices = data.get("choices") if isinstance(data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise LLMAPIError("OpenRouter вернул ответ без choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None

    if isinstance(content, list):  # некоторые модели отдают список частей
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    if not isinstance(content, str) or not content.strip():
        raise LLMAPIError("OpenRouter вернул пустой content")
    return content


# ---------------------------------------------------------------------------
# Клиент
# ---------------------------------------------------------------------------

SleepFn = Callable[[float], Awaitable[None]]


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://openrouter.ai/api/v1",
        app_name: str = "css-tutor-bot",
        timeout: float = 30.0,
        max_retries: int = 3,
        client: httpx.AsyncClient | None = None,
        sleep: SleepFn | None = None,
    ) -> None:
        self._api_key = (api_key or "").strip()
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._app_name = app_name
        self._timeout = timeout
        self._attempts = max(1, int(max_retries))
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._sleep: SleepFn = sleep or asyncio.sleep

    @classmethod
    def from_config(cls, config: Any) -> "OpenRouterClient":
        return cls(
            api_key=config.openrouter_api_key,
            model=config.openrouter_model,
            base_url=config.openrouter_base_url,
            app_name=config.openrouter_app_name,
            timeout=config.ai_timeout_seconds,
            max_retries=config.ai_max_retries,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # -- public API ---------------------------------------------------------

    async def complete_json(
        self,
        messages: Sequence[dict[str, str]],
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        json_mode: bool = True,
    ) -> str:
        """Запрос chat completion с ожиданием JSON-ответа.

        Возвращает сырую строку ``content`` (парсинг — на стороне AI Teacher).
        """
        if not self._api_key:
            raise LLMConfigError("OPENROUTER_API_KEY не задан — запрос невозможен")

        payload = self._build_payload(messages, temperature, max_tokens, json_mode)
        try:
            return await self._request_with_retry(payload)
        except LLMAPIError as exc:
            if json_mode and exc.status_code == 400 and _mentions_json_mode(exc.body):
                log.warning("Модель не поддерживает response_format — повтор без него")
                payload.pop("response_format", None)
                return await self._request_with_retry(payload)
            raise

    # -- internals ----------------------------------------------------------

    def _build_payload(
        self,
        messages: Sequence[dict[str, str]],
        temperature: float,
        max_tokens: int | None,
        json_mode: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": list(messages),
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    def _headers(self) -> dict[str, str]:
        # Значение Authorization никогда не логируется.
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": self._app_name,
        }

    async def _request_with_retry(self, payload: dict[str, Any]) -> str:
        for attempt in range(1, self._attempts + 1):
            try:
                return await self._request_once(payload)
            except LLMRateLimitError as exc:
                if attempt >= self._attempts:
                    raise
                delay = exc.retry_after or self._backoff_delay(attempt)
                delay = min(delay, RETRY_AFTER_MAX_SECONDS)
                log.warning(
                    "OpenRouter rate limit (попытка %d/%d), пауза %.1fс",
                    attempt,
                    self._attempts,
                    delay,
                )
            except LLMRequestError:
                if attempt >= self._attempts:
                    raise
                delay = self._backoff_delay(attempt)
                log.warning(
                    "Сбой запроса к OpenRouter (попытка %d/%d), повтор через %.1fс",
                    attempt,
                    self._attempts,
                    delay,
                )
            except LLMAPIError as exc:
                retryable = exc.status_code is not None and 500 <= exc.status_code < 600
                if not retryable or attempt >= self._attempts:
                    raise
                delay = self._backoff_delay(attempt)
                log.warning(
                    "OpenRouter вернул %s (попытка %d/%d), повтор через %.1fс",
                    exc.status_code,
                    attempt,
                    self._attempts,
                    delay,
                )
            await self._sleep(delay)

        # Недостижимо: цикл либо возвращает результат, либо бросает исключение.
        raise LLMRequestError("не удалось выполнить запрос к OpenRouter")

    async def _request_once(self, payload: dict[str, Any]) -> str:
        url = f"{self._base_url}/chat/completions"
        try:
            response = await self._client.post(
                url, headers=self._headers(), json=payload, timeout=self._timeout
            )
        except httpx.TimeoutException as exc:
            raise LLMRequestError("таймаут запроса к OpenRouter") from exc
        except httpx.HTTPError as exc:
            raise LLMRequestError(
                f"сетевая ошибка OpenRouter: {type(exc).__name__}"
            ) from exc

        if response.status_code == 429:
            raise LLMRateLimitError(
                "OpenRouter rate limit", retry_after=_parse_retry_after(response)
            )
        if response.status_code >= 500:
            raise LLMAPIError(
                f"OpenRouter вернул {response.status_code}",
                status_code=response.status_code,
                body=_safe_body(response),
            )
        if response.status_code >= 400:
            raise LLMAPIError(
                f"OpenRouter вернул {response.status_code}: {_safe_body(response)}",
                status_code=response.status_code,
                body=_safe_body(response),
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMAPIError(
                "OpenRouter вернул не-JSON ответ", status_code=response.status_code
            ) from exc

        return _extract_content(data)

    @staticmethod
    def _backoff_delay(attempt: int) -> float:
        return min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_MAX_SECONDS)
