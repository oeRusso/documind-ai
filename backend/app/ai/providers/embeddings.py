"""EmbeddingProvider: text in, vector of numbers out (stage 6).

An embedding is a list of numbers (1024 for bge-m3) that places a text in a "meaning space":
texts that say similar things land close together, even with different words ("preaviso" and
"avisar con anticipación"). Searching by meaning = finding the chunks whose vectors are closest
to the question's vector.

The modules never talk to Ollama: they ask for this interface (CLAUDE.md, "Arquitectura").
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class EmbeddingModel:
    name: str  # as Ollama calls it
    dimension: int
    # Some models want a hint of what each text is ("query: ...", "passage: ..."). Ours do not.
    query_prefix: str = ""
    document_prefix: str = ""


# Models the database knows how to index (one HNSW index per model, see migration 0006).
KNOWN_MODELS: dict[str, EmbeddingModel] = {
    "bge-m3": EmbeddingModel("bge-m3", 1024),
    "paraphrase-multilingual": EmbeddingModel("paraphrase-multilingual", 768),
}


class UnknownEmbeddingModelError(ValueError):
    pass


def embedding_model(name: str) -> EmbeddingModel:
    try:
        return KNOWN_MODELS[name]
    except KeyError as exc:
        known = ", ".join(sorted(KNOWN_MODELS))
        raise UnknownEmbeddingModelError(f"{name!r} is not supported ({known})") from exc


class EmbeddingProvider(Protocol):
    @property
    def model(self) -> EmbeddingModel: ...

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector per text, in the same order."""
        ...

    async def embed_query(self, text: str) -> list[float]: ...
