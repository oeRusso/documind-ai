"""Build the configured AI providers from Settings (one place, used by the API and the worker)."""

from app.ai.providers.embeddings import EmbeddingProvider, embedding_model
from app.ai.providers.ollama import OllamaEmbeddingProvider
from app.core.config import Settings


def build_embedding_provider(settings: Settings) -> EmbeddingProvider | None:
    """None when no Ollama is configured: processing skips embeddings, search uses words only."""
    if not settings.ollama_base_url:
        return None
    return OllamaEmbeddingProvider(
        settings.ollama_base_url, embedding_model(settings.embedding_model)
    )
