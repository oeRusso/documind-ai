"""Embeddings and answers with a local Ollama server (HTTP API). Nothing leaves the server."""

import json
from collections.abc import AsyncIterator, Sequence

import httpx

from app.ai.providers.embeddings import EmbeddingModel
from app.ai.providers.llm import ChatMessage, LLMServiceError


class EmbeddingServiceError(RuntimeError):
    """Ollama did not answer or answered something unexpected (temporary: retry later)."""


class OllamaEmbeddingProvider:
    def __init__(
        self,
        base_url: str,
        model: EmbeddingModel,
        *,
        batch_size: int = 16,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._batch_size = batch_size
        self._timeout = timeout_seconds
        self._transport = transport  # tests pass a MockTransport

    @property
    def model(self) -> EmbeddingModel:
        return self._model

    async def _embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for start in range(0, len(texts), self._batch_size):
                batch = list(texts[start : start + self._batch_size])
                try:
                    response = await client.post(
                        f"{self._base_url}/api/embed",
                        json={"model": self._model.name, "input": batch, "truncate": True},
                    )
                    response.raise_for_status()
                    embeddings = response.json()["embeddings"]
                except (httpx.HTTPError, KeyError, ValueError) as exc:
                    raise EmbeddingServiceError(f"Ollama embeddings failed: {exc}") from exc
                if len(embeddings) != len(batch) or any(
                    len(vector) != self._model.dimension for vector in embeddings
                ):
                    raise EmbeddingServiceError("Ollama returned vectors of an unexpected shape")
                vectors.extend(embeddings)
        return vectors

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embed([self._model.document_prefix + text for text in texts])

    async def embed_query(self, text: str) -> list[float]:
        [vector] = await self._embed([self._model.query_prefix + text])
        return vector


class OllamaLLMProvider:
    """Chat with /api/chat in streaming mode: Ollama answers one JSON object per line."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        keep_alive: str = "30m",
        context_window: int = 4096,
        timeout_seconds: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._keep_alive = keep_alive
        self._context_window = context_window
        # Connecting must be fast; reading can wait (a CPU model may think before the first token).
        self._timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        self._transport = transport

    @property
    def model(self) -> str:
        return self._model

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "keep_alive": self._keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self._context_window,
            },
        }
        try:
            async with (
                httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client,
                client.stream("POST", f"{self._base_url}/api/chat", json=payload) as response,
            ):
                if response.status_code != httpx.codes.OK:
                    await response.aread()
                    raise LLMServiceError(f"Ollama chat answered {response.status_code}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise LLMServiceError(f"Ollama chat failed: {data['error']}")
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if data.get("done"):
                        return
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMServiceError(f"Ollama chat failed: {exc}") from exc
        raise LLMServiceError("Ollama chat ended without finishing the answer")

    async def warm_up(self) -> None:
        # A request without messages only loads the model (Ollama docs, "Load a model").
        try:
            async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as c:
                response = await c.post(
                    f"{self._base_url}/api/chat",
                    json={
                        "model": self._model,
                        "messages": [],
                        "keep_alive": self._keep_alive,
                        # Same context size as the answers: a different one reloads the model.
                        "options": {"num_ctx": self._context_window},
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LLMServiceError(f"Ollama could not load {self._model}: {exc}") from exc
