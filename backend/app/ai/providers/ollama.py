"""Embeddings with a local Ollama server (HTTP API /api/embed). Nothing leaves the server."""

from collections.abc import Sequence

import httpx

from app.ai.providers.embeddings import EmbeddingModel


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
