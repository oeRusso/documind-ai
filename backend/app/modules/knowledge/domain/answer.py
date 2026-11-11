"""What an answer is made of, as it is produced (stage 7). Pure Python.

The use case yields these events in order; the router turns each one into an SSE event:
  Queued* -> Token* -> CitationsReady -> Done
(Queued only if the question had to wait; no Token when the model wrote nothing.)
"""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Citation:
    marker: int  # the n of [n] in the answer
    document_id: UUID
    document_title: str
    page_start: int | None
    page_end: int | None
    excerpt: str  # the beginning of the cited text, to show it next to the answer


@dataclass(frozen=True, slots=True)
class Queued:
    position: int  # questions before this one (1 = next)


@dataclass(frozen=True, slots=True)
class Token:
    text: str


@dataclass(frozen=True, slots=True)
class CitationsReady:
    citations: list[Citation]


@dataclass(frozen=True, slots=True)
class Done:
    # True when the documents did not answer the question (with or without calling the model).
    no_evidence: bool


AnswerEvent = Queued | Token | CitationsReady | Done
