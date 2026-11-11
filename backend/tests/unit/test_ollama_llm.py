"""OllamaLLMProvider against a fake Ollama (httpx.MockTransport): no model, no network."""

import json

import httpx
import pytest

from app.ai.providers.llm import ChatMessage, LLMServiceError
from app.ai.providers.ollama import OllamaLLMProvider

MESSAGES = [ChatMessage("system", "Reglas"), ChatMessage("user", "¿Cuántos días?")]


def ndjson(*objects: object) -> bytes:
    return "\n".join(json.dumps(o) for o in objects).encode() + b"\n"


def provider(handler: httpx.MockTransport) -> OllamaLLMProvider:
    return OllamaLLMProvider("http://ollama:11434/", "tiny:1b", keep_alive="5m", transport=handler)


async def collect(llm: OllamaLLMProvider) -> list[str]:
    return [piece async for piece in llm.stream(MESSAGES, max_tokens=64)]


async def test_streams_the_pieces_and_sends_the_options() -> None:
    seen: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        body = ndjson(
            {"message": {"role": "assistant", "content": "Son "}, "done": False},
            {"message": {"role": "assistant", "content": "30 días [1]."}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True, "eval_count": 5},
        )
        return httpx.Response(200, content=body)

    assert await collect(provider(httpx.MockTransport(handle))) == ["Son ", "30 días [1]."]
    assert seen["url"] == "http://ollama:11434/api/chat"
    body = seen["body"]
    assert isinstance(body, dict)
    assert body["model"] == "tiny:1b"
    assert body["stream"] is True
    assert body["keep_alive"] == "5m"
    assert body["options"]["num_predict"] == 64
    assert body["options"]["temperature"] == 0.0
    assert body["messages"][0] == {"role": "system", "content": "Reglas"}


async def test_an_error_status_raises() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(404, json={"error": "not found"}))
    with pytest.raises(LLMServiceError, match="404"):
        await collect(provider(transport))


async def test_an_error_in_the_middle_of_the_stream_raises() -> None:
    body = ndjson({"message": {"content": "Hola"}, "done": False}, {"error": "out of memory"})
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    with pytest.raises(LLMServiceError, match="out of memory"):
        await collect(provider(transport))


async def test_a_stream_cut_before_done_raises() -> None:
    body = ndjson({"message": {"content": "Hola"}, "done": False})
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    with pytest.raises(LLMServiceError, match="without finishing"):
        await collect(provider(transport))


async def test_a_connection_error_raises() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(LLMServiceError, match="refused"):
        await collect(provider(httpx.MockTransport(handle)))


async def test_warm_up_loads_the_model_without_messages() -> None:
    seen: list[dict[str, object]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"done": True})

    await provider(httpx.MockTransport(handle)).warm_up()
    assert seen == [{"model": "tiny:1b", "messages": [], "keep_alive": "5m"}]
