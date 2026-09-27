"""Тесты OpenRouter-клиента на mock HTTP (без реальной сети)."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from config import Config
from services.llm_client import (
    LLMAPIError,
    LLMConfigError,
    LLMRateLimitError,
    LLMRequestError,
    OpenRouterClient,
)

MESSAGES = [{"role": "user", "content": "hi"}]
CONTENT = '{"ok": true}'


class SleepRecorder:
    """Заменяет asyncio.sleep: запоминает паузы и не тормозит тесты."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def make_client(handler, *, max_retries: int = 3, sleep=None, api_key="sk-or-test"):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenRouterClient(
        api_key=api_key,
        model="test/model",
        max_retries=max_retries,
        client=http,
        sleep=sleep,
    )
    return client, http


def ok_handler(content: str = CONTENT, captured: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if captured is not None:
            captured.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return handler


async def test_successful_request() -> None:
    captured: list[httpx.Request] = []
    client, http = make_client(ok_handler(captured=captured))

    result = await client.complete_json(MESSAGES)

    assert result == CONTENT
    request = captured[0]
    assert request.method == "POST"
    assert request.url.path.endswith("/chat/completions")
    assert request.headers["authorization"] == "Bearer sk-or-test"
    body = json.loads(request.content)
    assert body["model"] == "test/model"
    assert body["messages"] == MESSAGES
    assert body["response_format"] == {"type": "json_object"}
    await http.aclose()


async def test_missing_api_key_raises_without_request() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={})

    client, http = make_client(handler, api_key="")
    with pytest.raises(LLMConfigError):
        await client.complete_json(MESSAGES)
    assert calls == []
    await http.aclose()


async def test_timeout_retries_then_fails() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.TimeoutException("timeout")

    sleep = SleepRecorder()
    client, http = make_client(handler, max_retries=3, sleep=sleep)

    with pytest.raises(LLMRequestError):
        await client.complete_json(MESSAGES)

    assert len(calls) == 3  # ограниченное число попыток
    assert len(sleep.delays) == 2  # паузы между попытками
    await http.aclose()


async def test_network_error_is_wrapped() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    client, http = make_client(handler, max_retries=1)
    with pytest.raises(LLMRequestError):
        await client.complete_json(MESSAGES)
    await http.aclose()


async def test_rate_limit_then_success_honours_retry_after() -> None:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] < 3:
            return httpx.Response(
                429, headers={"retry-after": "2"}, json={"error": {"message": "slow down"}}
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": CONTENT}}]})

    sleep = SleepRecorder()
    client, http = make_client(handler, max_retries=5, sleep=sleep)

    assert await client.complete_json(MESSAGES) == CONTENT
    assert sleep.delays == [2.0, 2.0]
    await http.aclose()


async def test_rate_limit_caps_retry_after() -> None:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "999"}, json={})
        return httpx.Response(200, json={"choices": [{"message": {"content": CONTENT}}]})

    sleep = SleepRecorder()
    client, http = make_client(handler, max_retries=3, sleep=sleep)

    await client.complete_json(MESSAGES)
    assert sleep.delays == [30.0]  # capped
    await http.aclose()


async def test_rate_limit_exhausted_raises() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429, json={})

    sleep = SleepRecorder()
    client, http = make_client(handler, max_retries=3, sleep=sleep)

    with pytest.raises(LLMRateLimitError):
        await client.complete_json(MESSAGES)
    assert len(calls) == 3
    await http.aclose()


async def test_server_error_retried_then_success() -> None:
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"choices": [{"message": {"content": CONTENT}}]})

    sleep = SleepRecorder()
    client, http = make_client(handler, max_retries=3, sleep=sleep)

    assert await client.complete_json(MESSAGES) == CONTENT
    assert len(sleep.delays) == 1
    await http.aclose()


async def test_client_error_not_retried() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "unauthorized"}})

    sleep = SleepRecorder()
    client, http = make_client(handler, max_retries=3, sleep=sleep)

    with pytest.raises(LLMAPIError) as exc:
        await client.complete_json(MESSAGES)
    assert exc.value.status_code == 401
    assert len(calls) == 1
    assert sleep.delays == []
    await http.aclose()


async def test_json_mode_fallback_on_400() -> None:
    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            return httpx.Response(
                400,
                json={"error": {"message": "response_format is not supported"}},
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": CONTENT}}]})

    client, http = make_client(handler)

    assert await client.complete_json(MESSAGES) == CONTENT
    assert "response_format" in bodies[0]
    assert "response_format" not in bodies[1]
    await http.aclose()


async def test_malformed_response_raises_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client, http = make_client(handler)
    with pytest.raises(LLMAPIError):
        await client.complete_json(MESSAGES)
    await http.aclose()


async def test_content_as_parts_list_is_joined() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": [{"text": "ab"}, {"text": "cd"}]}}]},
        )

    client, http = make_client(handler)
    assert await client.complete_json(MESSAGES) == "abcd"
    await http.aclose()


async def test_api_key_not_leaked_in_logs_or_errors(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401, json={"error": {"message": "bad key sk-or-test"}}
        )

    client, http = make_client(handler)

    with caplog.at_level(logging.DEBUG):
        with pytest.raises(LLMAPIError) as exc:
            await client.complete_json(MESSAGES)

    assert "sk-or-test" not in caplog.text
    assert "sk-or-test" not in str(exc.value)
    assert "REDACTED" in str(exc.value)
    await http.aclose()


def test_from_config_builds_client() -> None:
    config = Config(
        bot_token="1:x",
        openrouter_api_key="sk-or-abc",
        openrouter_model="openai/gpt-4o-mini",
    )
    client = OpenRouterClient.from_config(config)
    assert isinstance(client, OpenRouterClient)
