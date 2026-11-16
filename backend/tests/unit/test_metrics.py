"""Metrics from log events (stage 10): what each event adds, and GET /metrics."""

import httpx
from prometheus_client import REGISTRY

from app.core.metrics import metrics_from_logs


def value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def emit(**event: object) -> None:
    assert metrics_from_logs(None, "info", dict(event)) == event  # the log line is untouched


def test_an_answer_feeds_timings_results_and_citations() -> None:
    answered = value("documind_answers_total", result="answered")
    valid = value("documind_citations_total", valid="true")
    invalid = value("documind_citations_total", valid="false")
    first_token = value("documind_answer_first_token_seconds_count")

    emit(
        event="answer_generated",
        no_evidence=False,
        waited_ms=10,
        first_token_ms=1500,
        generation_ms=4000,
        answer_chars=80,
        citations=[{"marker": 1}, {"marker": 2}],
    )
    emit(event="invalid_citations_dropped", markers=[7])

    assert value("documind_answers_total", result="answered") == answered + 1
    assert value("documind_citations_total", valid="true") == valid + 2
    assert value("documind_citations_total", valid="false") == invalid + 1
    assert value("documind_answer_first_token_seconds_count") == first_token + 1


def test_pipeline_events_feed_their_metrics() -> None:
    ocr = value("documind_page_seconds_count", method="ocr")
    ready = value("documind_documents_total", result="ready")
    emit(event="page_ocr", ms=2500)
    emit(event="document_ready", chunks=3, pages=2)
    assert value("documind_page_seconds_count", method="ocr") == ocr + 1
    assert value("documind_documents_total", result="ready") == ready + 1


def test_a_strange_event_never_breaks_logging() -> None:
    emit(event="answer_generated", waited_ms="not a number", citations="nope")
    emit(event="something_else")


async def test_metrics_are_served_outside_the_api(offline_client: httpx.AsyncClient) -> None:
    await offline_client.get("/health")
    response = await offline_client.get("/metrics")
    assert response.status_code == 200
    assert "documind_answers_total" in response.text
    assert "http_requests_total" in response.text or "http_request_duration" in response.text
    openapi = (await offline_client.get("/openapi.json")).json()
    assert "/metrics" not in openapi["paths"]
