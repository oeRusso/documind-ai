"""Measure the answers: threshold, "no encontré", citations, speed and RAM, per LLM (stage 7).

    OLLAMA_URL=http://127.0.0.1:11435 uv run python -m evaluation.eval_answers
    ... --models granite3.3:2b llama3.2:3b --answerable 24 --threshold 0.5

(11435 is the Ollama container of compose, which has the LLMs; see compose.yaml.)

What it does, with the app's own code end to end (AnswerQuestion, the same as POST /chat):
1. Loads the corpus in a temporary organization of the TEST database (like eval_retrieval).
2. Threshold: runs the hybrid search (bge-m3) for every question and reports, for each
   candidate RAG_MIN_SCORE, how many unanswerable questions it stops before the LLM and how many
   answerable ones it wrongly stops. No LLM needed for this part.
3. For each LLM, answers a sample (every unanswerable question + `--answerable` answerable ones,
   spread over the dataset) and measures:
   - answerable: answered (not "no encontré"), cited the expected page, cited anything at all;
   - unanswerable: said "no encontré" (by threshold or by the model itself);
   - invalid citations dropped, time to first token, total time, characters per second;
   - peak RAM of the Ollama container (if `podman` is available).
4. Writes evaluation/results/answers.json (with every answer, to read them) and a report in
   docs/evaluation/.
"""

import argparse
import asyncio
import contextlib
import json
import os
import re
import statistics
import subprocess
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.ai.concurrency import GenerationQueue
from app.ai.providers.embeddings import EmbeddingProvider, embedding_model
from app.ai.providers.llm import LLMServiceError
from app.ai.providers.ollama import OllamaEmbeddingProvider, OllamaLLMProvider
from app.core.config import get_settings
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.knowledge.application.answer_question import (
    AnswerOptions,
    AnswerQuery,
    AnswerQuestion,
    PreparedAnswer,
)
from app.modules.knowledge.application.search_documents import SearchDocuments
from app.modules.knowledge.domain.answer import CitationsReady, Done, Token
from app.modules.knowledge.domain.citations import check_markers
from app.modules.knowledge.infrastructure.sql_search import SqlChunkSearch
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.shared.ids import new_id, utc_now
from evaluation.dataset import Question, load_questions
from evaluation.eval_retrieval import (
    BACKEND,
    REPORTS,
    Corpus,
    create_organization,
    delete_organization,
    load_corpus,
    test_database_urls,
)

HERE = Path(__file__).parent
RESULTS = HERE / "results" / "answers.json"
DEFAULT_MODELS = ["granite3.3:2b", "llama3.2:3b"]
THRESHOLDS = [round(0.40 + 0.01 * n, 2) for n in range(26)]  # 0.40 .. 0.65
_ANY_MARKER = re.compile(r"\[\s*\d")


@dataclass
class ThresholdRow:
    threshold: float
    unanswerable_stopped: int  # good: no LLM call, no invention
    answerable_stopped: int  # bad: a question the documents answer gets "no encontré"


@dataclass
class AnswerRecord:
    id: str
    question: str
    answerable: bool
    best_similarity: float | None
    stopped_by_threshold: bool
    answer: str
    no_evidence: bool
    cited_pages: list[str]  # "slug:start-end"
    cited_expected: bool
    invalid_markers: int
    first_token_s: float | None
    total_s: float
    error: str | None = None  # the model failed (out of memory, crash): counted, not fatal


@dataclass
class ModelResult:
    model: str
    answerable: int
    answered: int  # answerable questions that got an answer (not "no encontré")
    cited_expected: int  # ... and cited the page where the answer is
    without_citations: int  # answers with no valid citation at all
    unanswerable: int
    said_no_evidence: int
    invalid_markers: int
    errors: int
    first_token_s_p50: float
    total_s_p50: float
    total_s_p95: float
    chars_per_second: float
    peak_ram_gb: float | None
    records: list[AnswerRecord] = field(default_factory=list)


@contextlib.contextmanager
def ram_sampler(container: str) -> Iterator[list[float]]:
    """Samples the container's real memory every 2 s in a thread; yields the GB readings.

    It reads `anon` from the container's cgroup: memory the processes really hold. `podman stats`
    also counts file cache, which the kernel frees when needed (it shows the limit, not the use).
    """
    readings: list[float] = []
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            try:
                out = subprocess.run(  # noqa: S603 (fixed command, no shell)
                    ["podman", "exec", container, "cat", "/sys/fs/cgroup/memory.stat"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=True,
                ).stdout
                match = re.search(r"^anon (\d+)$", out, re.MULTILINE)
                if match:
                    readings.append(int(match.group(1)) / 1e9)
            except (OSError, subprocess.SubprocessError):
                return  # no podman here: no RAM figure
            stop.wait(2)

    thread = threading.Thread(target=sample, daemon=True)
    thread.start()
    try:
        yield readings
    finally:
        stop.set()
        thread.join(timeout=15)


def actor(corpus: Corpus) -> Membership:
    return Membership.create(
        id=new_id(),
        organization_id=corpus.organization_id,
        user_id=new_id(),
        role=Role.VIEWER,
        now=utc_now(),
    )


def sample(questions: list[Question], answerable: int) -> list[Question]:
    with_answer = [q for q in questions if q.answerable]
    step = max(1, len(with_answer) // max(1, answerable))
    chosen = with_answer[::step][:answerable]
    return chosen + [q for q in questions if not q.answerable]


# Builds the use case on a database session (as the API does on each request).
Build = Callable[[AsyncSession], AnswerQuestion]


async def prepare(
    engine: AsyncEngine, corpus: Corpus, build: Build, question: Question
) -> tuple[AnswerQuestion, PreparedAnswer]:
    async with AsyncSession(engine) as session, session.begin():
        await SqlTenantContext(session).set_organization(corpus.organization_id)
        use_case = build(session)
        return use_case, await use_case.prepare(AnswerQuery(actor(corpus), question.question))


async def calibrate(
    engine: AsyncEngine, corpus: Corpus, questions: list[Question], build: Build
) -> tuple[list[ThresholdRow], dict[str, float | None]]:
    best: dict[str, float | None] = {}
    for question in questions:
        _, prepared = await prepare(engine, corpus, build, question)
        best[question.id] = prepared.best_similarity
    rows = []
    for threshold in THRESHOLDS:
        rows.append(
            ThresholdRow(
                threshold,
                unanswerable_stopped=sum(
                    1 for q in questions if not q.answerable and (best[q.id] or 0) < threshold
                ),
                answerable_stopped=sum(
                    1 for q in questions if q.answerable and (best[q.id] or 0) < threshold
                ),
            )
        )
    return rows, best


async def run_model(
    engine: AsyncEngine,
    corpus: Corpus,
    questions: list[Question],
    llm: OllamaLLMProvider,
    build: Build,
    container: str,
) -> ModelResult:
    slugs = {document_id: slug for slug, document_id in corpus.document_ids.items()}
    records = []
    await llm.warm_up()
    with ram_sampler(container) as ram:
        for n, question in enumerate(questions, start=1):
            use_case, prepared = await prepare(engine, corpus, build, question)
            started = time.perf_counter()
            first: float | None = None
            text = ""
            cited: list[str] = []
            cited_expected = False
            no_evidence = False
            error: str | None = None
            try:
                async for event in use_case.stream(prepared):
                    if isinstance(event, Token):
                        first = first if first is not None else time.perf_counter() - started
                        text += event.text
                    elif isinstance(event, CitationsReady):
                        for c in event.citations:
                            slug = slugs[c.document_id]
                            cited.append(f"{slug}:{c.page_start}-{c.page_end}")
                            page = question.expected_page or 0
                            if slug == question.document and (c.page_start or 0) <= page <= (
                                c.page_end or 0
                            ):
                                cited_expected = True
                    elif isinstance(event, Done):
                        no_evidence = event.no_evidence
            except LLMServiceError as exc:
                error = str(exc)
            # Markers the model wrote that pointed nowhere (the filter already removed them).
            raw_invalid = 0
            if prepared.has_evidence:
                valid = {s.marker for s in prepared.sources}
                raw_invalid = len(check_markers(text, valid).invalid)
            records.append(
                AnswerRecord(
                    id=question.id,
                    question=question.question,
                    answerable=question.answerable,
                    best_similarity=prepared.best_similarity,
                    stopped_by_threshold=not prepared.has_evidence,
                    answer=text,
                    no_evidence=no_evidence,
                    cited_pages=cited,
                    cited_expected=cited_expected,
                    invalid_markers=raw_invalid,
                    first_token_s=round(first, 2) if first is not None else None,
                    total_s=round(time.perf_counter() - started, 2),
                    error=error,
                )
            )
            r = records[-1]
            print(
                f"  [{n}/{len(questions)}] {question.id} {r.total_s:5.1f}s "
                f"{'ERROR' if r.error else 'NO-EVIDENCIA' if r.no_evidence else 'respondió'}"
                f"{' cita-ok' if r.cited_expected else ''}"
            )

    generated = [r for r in records if not r.stopped_by_threshold and not r.error]
    answerable = [r for r in records if r.answerable]
    unanswerable = [r for r in records if not r.answerable]
    totals = sorted(r.total_s for r in generated) or [0.0]
    firsts = [r.first_token_s for r in generated if r.first_token_s is not None] or [0.0]
    chars = sum(len(r.answer) for r in generated)
    return ModelResult(
        model=llm.model,
        answerable=len(answerable),
        answered=sum(1 for r in answerable if not r.no_evidence and not r.error),
        cited_expected=sum(1 for r in answerable if r.cited_expected),
        without_citations=sum(
            1
            for r in records
            if not r.error and not r.no_evidence and not _ANY_MARKER.search(r.answer)
        ),
        unanswerable=len(unanswerable),
        said_no_evidence=sum(1 for r in unanswerable if r.no_evidence),
        invalid_markers=sum(r.invalid_markers for r in records),
        errors=sum(1 for r in records if r.error),
        first_token_s_p50=round(statistics.median(firsts), 1),
        total_s_p50=round(statistics.median(totals), 1),
        total_s_p95=round(totals[max(0, int(len(totals) * 0.95) - 1)], 1),
        chars_per_second=round(chars / max(0.001, sum(r.total_s for r in generated)), 1),
        peak_ram_gb=round(max(ram), 2) if ram else None,
        records=records,
    )


def write_report(
    rows: list[ThresholdRow],
    threshold: float,
    results: list[ModelResult],
    questions: list[Question],
    context_tokens: int,
) -> Path:
    today = datetime.now(UTC).date().isoformat()
    answerable = sum(1 for q in questions if q.answerable)
    lines = [
        f"# Evaluación de respuestas — {today}",
        "",
        "Generado por `uv run python -m evaluation.eval_answers` (etapa 7). No editar a mano.",
        "",
        "## Umbral de «no encontré evidencia» (RAG_MIN_SCORE)",
        "",
        f"Similitud por significado (bge-m3) del fragmento más cercano, en las {len(questions)} "
        f"preguntas ({answerable} con respuesta, {len(questions) - answerable} sin respuesta). "
        "Bajo el umbral se responde «no encontré» sin llamar al modelo.",
        "",
        "| Umbral | sin respuesta frenadas (bien) | con respuesta frenadas (mal) |",
        "|---|---|---|",
    ]
    for row in rows:
        mark = " ← elegido" if row.threshold == threshold else ""
        lines.append(
            f"| {row.threshold:.2f}{mark} | {row.unanswerable_stopped} | {row.answerable_stopped} |"
        )
    lines += [
        "",
        "## Modelos",
        "",
        f"Muestra: todas las preguntas sin respuesta y una parte de las con respuesta, "
        f"repartidas en el dataset. Umbral {threshold}, contexto de {context_tokens} tokens. "
        "En la PC de desarrollo (CPU, sin GPU): en el VPS será más lento.",
        "",
        "| Modelo | respondió (con respuesta) | citó la página correcta | sin citas | "
        "dijo «no encontré» (sin respuesta) | citas inválidas | errores | 1er token p50 | "
        "total p50 | total p95 | caracteres/s | RAM pico Ollama |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        ram = f"{r.peak_ram_gb} GB" if r.peak_ram_gb is not None else "-"
        lines.append(
            f"| {r.model} | {r.answered}/{r.answerable} | {r.cited_expected}/{r.answerable} | "
            f"{r.without_citations} | {r.said_no_evidence}/{r.unanswerable} | "
            f"{r.invalid_markers} | {r.errors} | {r.first_token_s_p50} s | {r.total_s_p50} s | "
            f"{r.total_s_p95} s | {r.chars_per_second} | {ram} |"
        )
    lines += [
        "",
        "- **respondió**: no dijo «no encontré» (por umbral o por el modelo).",
        "- **citó la página correcta**: alguna cita apunta al documento y la página esperados.",
        "- **citas inválidas**: marcadores que no apuntaban a ningún fragmento entregado (el "
        "filtro los quitó del texto).",
        "- RAM: memoria real del contenedor de Ollama (`anon` del cgroup), con bge-m3 cargado a "
        "la vez (los dos modelos conviven) y la caché de prompts de llama.cpp apagada.",
        "",
        "Las respuestas completas están en `backend/evaluation/results/answers.json`.",
    ]
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"answers-{today}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


async def evaluate(args: argparse.Namespace) -> None:
    settings = get_settings()
    app_url, migrator_url = test_database_urls()
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["url"] = migrator_url
    await asyncio.to_thread(command.upgrade, config, "head")

    ollama = os.environ.get("OLLAMA_URL") or "http://127.0.0.1:11435"
    embeddings: EmbeddingProvider = OllamaEmbeddingProvider(
        ollama, embedding_model("bge-m3"), batch_size=32
    )
    engine = create_async_engine(app_url, poolclass=NullPool)
    migrator = create_async_engine(migrator_url, poolclass=NullPool)
    organization_id = await create_organization(migrator)
    options = AnswerOptions(
        min_score=args.threshold,
        context_tokens=settings.rag_context_tokens,
        max_answer_tokens=settings.rag_max_answer_tokens,
    )

    queue = GenerationQueue(1)

    def builder(llm: OllamaLLMProvider, min_score: float) -> Build:
        answer_options = AnswerOptions(min_score, options.context_tokens, options.max_answer_tokens)
        return lambda session: AnswerQuestion(
            SearchDocuments(SqlChunkSearch(session), embeddings), llm, queue, answer_options
        )

    try:
        print("Cargando el corpus…")
        corpus = await load_corpus(engine, organization_id, [embeddings])
        questions = load_questions()
        first = OllamaLLMProvider(ollama, args.models[0])
        rows, _ = await calibrate(engine, corpus, questions, builder(first, 0.0))
        for row in rows:
            print(
                f"umbral {row.threshold:.2f}: sin respuesta frenadas {row.unanswerable_stopped}"
                f", con respuesta frenadas {row.answerable_stopped}"
            )
        chosen = sample(questions, args.answerable)
        results = []
        for model in args.models:
            print(f"Modelo {model} ({len(chosen)} preguntas)…")
            llm = OllamaLLMProvider(ollama, model, keep_alive="5m")
            results.append(
                await run_model(
                    engine, corpus, chosen, llm, builder(llm, args.threshold), args.container
                )
            )
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(
            json.dumps(
                {"thresholds": [asdict(r) for r in rows], "models": [asdict(r) for r in results]},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        for r in results:
            print(
                f"{r.model:16} respondió {r.answered}/{r.answerable} cita-ok "
                f"{r.cited_expected}/{r.answerable} no-encontré {r.said_no_evidence}/"
                f"{r.unanswerable} p50 {r.total_s_p50}s RAM {r.peak_ram_gb}"
            )
        print(
            "Informe:",
            write_report(rows, args.threshold, results, questions, options.context_tokens),
        )
    finally:
        await delete_organization(migrator, organization_id)
        await engine.dispose()
        await migrator.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--answerable", type=int, default=24)
    parser.add_argument("--threshold", type=float, default=get_settings().rag_min_score)
    parser.add_argument("--container", default="documind-ollama-1")
    asyncio.run(evaluate(parser.parse_args()))


if __name__ == "__main__":
    main()
