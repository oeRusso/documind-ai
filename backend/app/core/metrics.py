"""Prometheus metrics (stage 10), built from the events the code already logs.

The use cases do not know Prometheus: they log what happened ("page_extracted", "answer_generated"
with its timings) and a structlog processor turns those events into metrics. One place to read
what is measured, and nothing to change in the domain to add a metric. In PHP terms: like a
log handler that, besides writing the line, adds one to a counter.

- API: `install_api_metrics(app)` adds request metrics (prometheus-fastapi-instrumentator) and
  serves everything at GET /metrics. Outside /api/v1 and never routed by Caddy: only Prometheus,
  inside the private network, reads it.
- Worker: `start_worker_metrics(port)` serves them on its own port (it has no web server).
"""

import contextlib
from collections.abc import Callable

from fastapi import FastAPI
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from prometheus_fastapi_instrumentator import Instrumentator
from structlog.typing import EventDict, WrappedLogger

_SECONDS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 30, 60, 120)
_SHORT = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5)

# --- Pipeline (worker) ---------------------------------------------------------------------
PAGE_SECONDS = Histogram(
    "documind_page_seconds", "Time to read one page", ["method"], buckets=_SECONDS
)  # method: text | ocr
DOCUMENTS = Counter("documind_documents_total", "Documents processed", ["result"])  # ready|failed
EMBEDDING_SECONDS = Histogram(
    "documind_embedding_seconds", "Time to embed the chunks of a document", buckets=_SECONDS
)
CHUNKS_EMBEDDED = Counter("documind_chunks_embedded_total", "Chunks with an embedding")
HIDDEN_TEXT = Counter("documind_hidden_text_pages_total", "PDF pages with hidden text dropped")

# --- Search and answers (API) --------------------------------------------------------------
SEARCH_SECONDS = Histogram(
    "documind_search_seconds", "Hybrid search before answering", buckets=_SHORT
)
QUEUE_WAIT_SECONDS = Histogram(
    "documind_answer_queue_wait_seconds", "Wait for a free place to generate", buckets=_SECONDS
)
FIRST_TOKEN_SECONDS = Histogram(
    "documind_answer_first_token_seconds", "From the start of generation", buckets=_SECONDS
)
GENERATION_SECONDS = Histogram(
    "documind_answer_generation_seconds", "Whole generation", buckets=_SECONDS
)
CHARS_PER_SECOND = Histogram(
    "documind_answer_chars_per_second",
    "Generation speed (characters; Ollama does not report tokens in the stream)",
    buckets=(2, 5, 10, 15, 20, 30, 50, 100),
)
ANSWERS = Counter(
    "documind_answers_total", "Answers", ["result"]
)  # answered | no_evidence (model said so) | below_threshold (model not called) | failed
CITATIONS = Counter("documind_citations_total", "Citation markers", ["valid"])  # true | false
UNSAFE_OUTPUT = Counter("documind_unsafe_output_total", "Answers with HTML or images removed")
GENERATION_WAITING = Gauge("documind_generation_waiting", "Questions waiting for the model")


def _seconds(event: EventDict, key: str) -> float | None:
    value = event.get(key)
    return float(value) / 1000 if isinstance(value, int | float) else None


def _answer_generated(event: EventDict) -> None:
    ANSWERS.labels("no_evidence" if event.get("no_evidence") else "answered").inc()
    for key, histogram in (
        ("waited_ms", QUEUE_WAIT_SECONDS),
        ("first_token_ms", FIRST_TOKEN_SECONDS),
        ("generation_ms", GENERATION_SECONDS),
    ):
        if (seconds := _seconds(event, key)) is not None:
            histogram.observe(seconds)
    generation = _seconds(event, "generation_ms")
    chars = event.get("answer_chars")
    if generation and isinstance(chars, int) and chars:
        CHARS_PER_SECOND.observe(chars / generation)
    citations = event.get("citations")
    if isinstance(citations, list) and citations:
        CITATIONS.labels("true").inc(len(citations))


def _observe(histogram: Histogram, key: str, *labels: str) -> Callable[[EventDict], None]:
    def record(event: EventDict) -> None:
        seconds = _seconds(event, key)
        if seconds is not None:
            (histogram.labels(*labels) if labels else histogram).observe(seconds)

    return record


def _count_list(counter: Counter, key: str, *labels: str) -> Callable[[EventDict], None]:
    def record(event: EventDict) -> None:
        items = event.get(key)
        if isinstance(items, list):
            (counter.labels(*labels) if labels else counter).inc(len(items))

    return record


def _embedded(event: EventDict) -> None:
    if isinstance(seconds := event.get("seconds"), int | float):
        EMBEDDING_SECONDS.observe(float(seconds))
    if isinstance(chunks := event.get("chunks"), int):
        CHUNKS_EMBEDDED.inc(chunks)


_HANDLERS: dict[str, Callable[[EventDict], None]] = {
    "page_extracted": _observe(PAGE_SECONDS, "ms", "text"),
    "page_ocr": _observe(PAGE_SECONDS, "ms", "ocr"),
    "document_ready": lambda _: DOCUMENTS.labels("ready").inc(),
    "extraction_failed": lambda _: DOCUMENTS.labels("failed").inc(),
    "chunks_embedded": _embedded,
    "hidden_text_dropped": lambda _: HIDDEN_TEXT.inc(),
    "answer_prepared": _observe(SEARCH_SECONDS, "search_ms"),
    "answer_generated": _answer_generated,
    "answer_without_evidence": lambda _: ANSWERS.labels("below_threshold").inc(),
    "answer_failed": lambda _: ANSWERS.labels("failed").inc(),
    "invalid_citations_dropped": _count_list(CITATIONS, "markers", "false"),
    "unsafe_output_removed": lambda _: UNSAFE_OUTPUT.inc(),
}


def metrics_from_logs(_logger: WrappedLogger, _method: str, event: EventDict) -> EventDict:
    """structlog processor: never changes the log line, never breaks it."""
    handler = _HANDLERS.get(str(event.get("event")))
    if handler is not None:
        with contextlib.suppress(Exception):  # a metric must never break logging
            handler(event)
    return event


def install_api_metrics(app: FastAPI, waiting: Callable[[], int]) -> None:
    GENERATION_WAITING.set_function(waiting)
    Instrumentator(
        excluded_handlers=["/metrics", "/health", "/ready"],
        should_group_status_codes=True,
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def start_worker_metrics(port: int) -> None:
    start_http_server(port)  # inside the container network only (compose)
