"""LLMProvider: messages in, text out, piece by piece (stage 7).

A language model writes text one "token" (a piece of a word) at a time. Streaming those pieces
lets the user read the answer while it is being written, instead of staring at a spinner.

The modules never talk to Ollama: they ask for this interface (CLAUDE.md, "Arquitectura").
"""

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Role
    content: str


class LLMServiceError(RuntimeError):
    """The model did not answer or answered something unexpected (temporary: retry later)."""


class LLMProvider(Protocol):
    @property
    def model(self) -> str: ...

    def stream(
        self,
        messages: Sequence[ChatMessage],
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> AsyncIterator[str]:
        """The answer, as it is generated. Raises LLMServiceError if the model fails."""
        ...

    async def warm_up(self) -> None:
        """Load the model in memory now, so the first question does not wait for it."""
        ...
