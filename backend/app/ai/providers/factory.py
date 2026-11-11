"""Build the configured AI providers from Settings (one place, used by the API and the worker)."""

from app.ai.providers.embeddings import EmbeddingProvider, embedding_model
from app.ai.providers.llm import LLMProvider
from app.ai.providers.ollama import OllamaEmbeddingProvider, OllamaLLMProvider
from app.core.config import Settings


def build_embedding_provider(settings: Settings) -> EmbeddingProvider | None:
    """None when no Ollama is configured: processing skips embeddings, search uses words only."""
    if not settings.ollama_url:
        return None
    return OllamaEmbeddingProvider(settings.ollama_url, embedding_model(settings.embedding_model))


def build_llm_provider(settings: Settings) -> LLMProvider | None:
    """None when no Ollama is configured: the chat answers that it is not available."""
    if not settings.ollama_url:
        return None
    return OllamaLLMProvider(
        settings.ollama_url, settings.llm_model, keep_alive=settings.llm_keep_alive
    )
