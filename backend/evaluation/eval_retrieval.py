"""Measure the search: recall@5, recall@10, MRR and latency, per mode and embedding model.

    uv run python -m evaluation.eval_retrieval                       # all modes and models
    uv run python -m evaluation.eval_retrieval --models bge-m3       # one model
    uv run python -m evaluation.eval_retrieval --text-only           # no Ollama needed (CI)

What it does, with the app's own code end to end:
1. Creates a temporary organization in the TEST database (<database>_test), never the real one.
2. Reads the corpus PDFs, cleans and chunks them exactly like the worker does.
3. Computes the embeddings with Ollama (OLLAMA_URL, default http://127.0.0.1:11434),
   caching them in evaluation/.cache so a re-run is fast.
4. Runs every question through SearchDocuments in each mode. A result is relevant when it is
   the expected document and its pages include the expected page.
5. Deletes the temporary organization and writes evaluation/results/retrieval.json plus a
   readable report in docs/evaluation/.
"""

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import NullPool, insert, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.ai.evaluation.metrics import first_relevant_rank, mean_reciprocal_rank, recall_at_k
from app.ai.providers.embeddings import EmbeddingProvider, embedding_model
from app.ai.providers.ollama import OllamaEmbeddingProvider
from app.core.config import get_settings
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.documents.domain.entities import Document, DocumentVersion, FileKind
from app.modules.documents.infrastructure.sql_repository import SqlDocumentRepository
from app.modules.extraction.domain.normalization import normalize_pages
from app.modules.extraction.infrastructure.readers import FileTextExtractor
from app.modules.ingestion.domain.chunking import Chunk, chunk_blocks
from app.modules.ingestion.domain.ports import ChunkVectors
from app.modules.ingestion.infrastructure.models import ChunkEmbeddingModel, DocumentChunkModel
from app.modules.ingestion.infrastructure.sql_repository import SqlChunkRepository
from app.modules.knowledge.application.search_documents import SearchDocuments, SearchQuery
from app.modules.knowledge.domain.search import SearchMode
from app.modules.knowledge.infrastructure.sql_search import SqlChunkSearch
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.shared.ids import new_id, utc_now
from evaluation.dataset import CORPUS, Question, corpus_documents, load_questions

HERE = Path(__file__).parent
BACKEND = HERE.parent
CACHE = HERE / ".cache" / "embeddings"
RESULTS = HERE / "results" / "retrieval.json"
REPORTS = BACKEND.parent / "docs" / "evaluation"
DEFAULT_MODELS = ["bge-m3", "paraphrase-multilingual"]


def test_database_urls() -> tuple[str, str]:
    """(app role, migrator role) URLs of <database>_test, built from the usual settings."""
    settings = get_settings()

    def to_test(url: str) -> str:
        parsed = make_url(url)
        return parsed.set(database=f"{parsed.database}_test").render_as_string(hide_password=False)

    return to_test(str(settings.database_url)), to_test(str(settings.database_migration_url))


@dataclass
class Corpus:
    organization_id: UUID
    document_ids: dict[str, UUID]  # slug -> id
    chunks: dict[str, list[Chunk]]  # slug -> chunks


async def create_organization(migrator: AsyncEngine) -> UUID:
    organization_id = new_id()
    async with migrator.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": str(organization_id)}
        )
        await connection.execute(
            text("INSERT INTO organizations (id, name, slug) VALUES (:id, :name, :slug)"),
            {
                "id": organization_id,
                "name": "Evaluación",
                "slug": f"eval-{organization_id.hex[:12]}",
            },
        )
    return organization_id


async def delete_organization(migrator: AsyncEngine, organization_id: UUID) -> None:
    async with migrator.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.current_org', :org, true)"), {"org": str(organization_id)}
        )
        await connection.execute(
            text("DELETE FROM organizations WHERE id = :id"), {"id": organization_id}
        )


def read_chunks(slug: str) -> list[Chunk]:
    with FileTextExtractor().open(CORPUS / f"{slug}.pdf", FileKind.PDF) as reader:
        pages = [reader.read_page(i) for i in range(reader.page_count)]
    return chunk_blocks(normalize_pages(pages))


def embedding_text(chunk: Chunk) -> str:
    """The same text the worker embeds (ProcessDocumentVersion._embed)."""
    return f"{chunk.section}\n\n{chunk.content}" if chunk.section else chunk.content


async def embed_cached(provider: EmbeddingProvider, texts: list[str]) -> list[list[float]]:
    digest = hashlib.sha256("\x00".join(texts).encode()).hexdigest()[:16]
    path = CACHE / f"{provider.model.name}-{digest}.json"
    if path.exists():
        cached: list[list[float]] = json.loads(path.read_text())
        return cached
    vectors = await provider.embed_documents(texts)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vectors))
    return vectors


async def load_corpus(
    engine: AsyncEngine, organization_id: UUID, providers: list[EmbeddingProvider]
) -> Corpus:
    corpus = Corpus(organization_id, {}, {})
    for slug in corpus_documents():
        chunks = read_chunks(slug)
        texts = [embedding_text(c) for c in chunks]
        vectors = {p.model.name: await embed_cached(p, texts) for p in providers}
        now = utc_now()
        document = Document.create(
            id=new_id(),
            organization_id=organization_id,
            title=slug,
            created_by_id=new_id(),
            now=now,
        )
        document = Document(**{**asdict(document), "created_by_id": None})
        version = DocumentVersion(
            id=new_id(),
            organization_id=organization_id,
            document_id=document.id,
            number=1,
            storage_key=f"{organization_id}/{new_id()}",
            filename=f"{slug}.pdf",
            sha256=hashlib.sha256(slug.encode()).hexdigest(),
            kind=FileKind.PDF,
            size_bytes=1,
            page_count=None,
            uploaded_by_id=None,
            created_at=now,
        )
        async with AsyncSession(engine) as session, session.begin():
            await SqlTenantContext(session).set_organization(organization_id)
            await SqlDocumentRepository(session).add(document, version)
            first = providers[0].model.name if providers else None
            await SqlChunkRepository(session).replace_for_version(
                organization_id,
                document.id,
                version.id,
                chunks,
                ChunkVectors(first, vectors[first]) if first else None,
            )
            ids = list(
                await session.scalars(
                    select(DocumentChunkModel.id)
                    .where(DocumentChunkModel.document_id == document.id)
                    .order_by(DocumentChunkModel.position)
                )
            )
            for provider in providers[1:]:
                name = provider.model.name
                await session.execute(
                    insert(ChunkEmbeddingModel),
                    [
                        {
                            "id": new_id(),
                            "organization_id": organization_id,
                            "document_id": document.id,
                            "chunk_id": chunk_id,
                            "model": name,
                            "embedding": vector,
                        }
                        for chunk_id, vector in zip(ids, vectors[name], strict=True)
                    ],
                )
        corpus.document_ids[slug] = document.id
        corpus.chunks[slug] = chunks
        print(f"  {slug}: {len(chunks)} fragmentos")
    return corpus


@dataclass
class ModeResult:
    name: str
    mode: str
    model: str | None
    recall_at_5: float
    recall_at_10: float
    mrr: float
    latency_ms_p50: float
    latency_ms_p95: float
    # Top-1 score of answerable vs unanswerable questions (stage 7 will need a threshold).
    top_score_answerable_median: float | None
    top_score_unanswerable_median: float | None
    misses: list[str]
    # recall@5 and MRR per kind of question ("natural", "keywords").
    by_kind: dict[str, dict[str, float]]


async def run_mode(
    engine: AsyncEngine,
    corpus: Corpus,
    questions: list[Question],
    mode: SearchMode,
    provider: EmbeddingProvider | None,
) -> ModeResult:
    actor = Membership.create(
        id=new_id(),
        organization_id=corpus.organization_id,
        user_id=new_id(),
        role=Role.VIEWER,
        now=utc_now(),
    )
    ranks: list[int | None] = []
    ranks_by_kind: dict[str, list[int | None]] = {}
    latencies: list[float] = []
    top_answerable: list[float] = []
    top_unanswerable: list[float] = []
    misses = []
    for question in questions:
        async with AsyncSession(engine) as session, session.begin():
            await SqlTenantContext(session).set_organization(corpus.organization_id)
            started = time.perf_counter()
            result = await SearchDocuments(SqlChunkSearch(session), provider).execute(
                SearchQuery(actor, question.question, mode=mode, limit=10)
            )
            latencies.append((time.perf_counter() - started) * 1000)
        top = result.hits[0].match.score if result.hits else None
        if not question.answerable:
            if top is not None:
                top_unanswerable.append(top)
            continue
        if top is not None:
            top_answerable.append(top)
        expected = corpus.document_ids[question.document or ""]
        relevant = [
            hit.match.document_id == expected
            and hit.match.page_start is not None
            and hit.match.page_start <= (question.expected_page or 0) <= (hit.match.page_end or 0)
            for hit in result.hits
        ]
        rank = first_relevant_rank(relevant)
        ranks.append(rank)
        ranks_by_kind.setdefault(question.kind, []).append(rank)
        if rank is None or rank > 5:
            misses.append(question.id)

    model = provider.model.name if provider and mode is not SearchMode.TEXT else None
    latencies.sort()
    # Vector scores are similarities; with fusion they are RRF scores: only medians, for reference.
    return ModeResult(
        name=f"{mode.value}" + (f" ({model})" if model else ""),
        mode=mode.value,
        model=model,
        recall_at_5=round(recall_at_k(ranks, 5), 3),
        recall_at_10=round(recall_at_k(ranks, 10), 3),
        mrr=round(mean_reciprocal_rank(ranks), 3),
        latency_ms_p50=round(statistics.median(latencies), 1),
        latency_ms_p95=round(latencies[int(len(latencies) * 0.95) - 1], 1),
        top_score_answerable_median=(
            round(statistics.median(top_answerable), 4) if top_answerable else None
        ),
        top_score_unanswerable_median=(
            round(statistics.median(top_unanswerable), 4) if top_unanswerable else None
        ),
        misses=misses,
        by_kind={
            kind: {
                "questions": len(kind_ranks),
                "recall_at_5": round(recall_at_k(kind_ranks, 5), 3),
                "mrr": round(mean_reciprocal_rank(kind_ranks), 3),
            }
            for kind, kind_ranks in sorted(ranks_by_kind.items())
        },
    )


def write_report(results: list[ModeResult], corpus: Corpus, questions: list[Question]) -> Path:
    today = datetime.now(UTC).date().isoformat()
    answerable = sum(1 for q in questions if q.answerable)
    chunks = sum(len(c) for c in corpus.chunks.values())
    lines = [
        f"# Evaluación de búsqueda — {today}",
        "",
        "Generado por `uv run python -m evaluation.eval_retrieval` (etapa 6). No editar a mano.",
        "",
        f"- Corpus: {len(corpus.chunks)} leyes de Infoleg, {chunks} fragmentos.",
        f"- Preguntas: {answerable} con respuesta y {len(questions) - answerable} sin respuesta.",
        "- Un resultado es relevante si es el documento esperado y sus páginas incluyen la página "
        "esperada.",
        "- Latencia: búsqueda completa (incluye calcular el embedding de la pregunta), en la PC de "
        "desarrollo.",
        "",
        "| Modo | recall@5 | recall@10 | MRR | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | {r.recall_at_5:.3f} | {r.recall_at_10:.3f} | {r.mrr:.3f} "
            f"| {r.latency_ms_p50:.0f} | {r.latency_ms_p95:.0f} |"
        )
    kinds = sorted({kind for r in results for kind in r.by_kind})
    lines += ["", "Por tipo de pregunta (recall@5 / MRR):", ""]
    lines += ["| Modo | " + " | ".join(kinds) + " |", "|---|" + "---|" * len(kinds)]
    for r in results:
        cells = [
            f"{r.by_kind[k]['recall_at_5']:.3f} / {r.by_kind[k]['mrr']:.3f}"
            if k in r.by_kind
            else "-"
            for k in kinds
        ]
        lines.append(f"| {r.name} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "`natural`: preguntas en lenguaje cotidiano. `keywords`: términos exactos o números de "
        "artículo, como también se busca.",
    ]
    lines += [
        "",
        "Puntaje del primer resultado (mediana), con y sin respuesta en el corpus. En modo "
        "vector es la similitud coseno; en texto, el rango de PostgreSQL; en híbrido, el puntaje "
        "propio del método que trajo ese fragmento. Sirve para elegir el umbral de «no encontré» "
        "de la etapa 7:",
        "",
    ]
    lines += ["| Modo | con respuesta | sin respuesta |", "|---|---|---|"]
    for r in results:
        lines.append(
            f"| {r.name} | {r.top_score_answerable_median} | {r.top_score_unanswerable_median} |"
        )
    lines += ["", "Preguntas fuera del top 5 por modo:", ""]
    for r in results:
        lines.append(f"- **{r.name}**: {', '.join(r.misses) or 'ninguna'}")
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"retrieval-{today}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


async def evaluate(models: list[str], text_only: bool) -> list[ModeResult]:
    app_url, migrator_url = test_database_urls()
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["url"] = migrator_url
    await asyncio.to_thread(command.upgrade, config, "head")

    ollama = os.environ.get("OLLAMA_URL") or "http://127.0.0.1:11434"
    providers: list[EmbeddingProvider] = (
        []
        if text_only
        else [OllamaEmbeddingProvider(ollama, embedding_model(m), batch_size=32) for m in models]
    )
    engine = create_async_engine(app_url, poolclass=NullPool)
    migrator = create_async_engine(migrator_url, poolclass=NullPool)
    organization_id = await create_organization(migrator)
    try:
        print("Cargando el corpus…")
        corpus = await load_corpus(engine, organization_id, providers)
        questions = load_questions()
        results = [await run_mode(engine, corpus, questions, SearchMode.TEXT, None)]
        for provider in providers:
            # Warm the model up: the first call loads it into memory and is not a search.
            await provider.embed_query("calentamiento")
            for mode in (SearchMode.VECTOR, SearchMode.HYBRID):
                results.append(await run_mode(engine, corpus, questions, mode, provider))
        for r in results:
            kinds = " ".join(
                f"{k}={v['recall_at_5']:.2f}/{v['mrr']:.2f}" for k, v in r.by_kind.items()
            )
            print(
                f"{r.name:34} recall@5={r.recall_at_5:.3f} MRR={r.mrr:.3f} "
                f"p95={r.latency_ms_p95:.0f}ms  {kinds}"
            )
        if not text_only:  # the committed results are always a full run
            RESULTS.parent.mkdir(parents=True, exist_ok=True)
            RESULTS.write_text(
                json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2) + "\n"
            )
            print("Informe:", write_report(results, corpus, questions))
        return results
    finally:
        await delete_organization(migrator, organization_id)
        await engine.dispose()
        await migrator.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--text-only", action="store_true", help="words only (no Ollama)")
    parser.add_argument(
        "--min-text-recall", type=float, default=0.0, help="fail if text recall@5 is lower (CI)"
    )
    args = parser.parse_args()
    results = asyncio.run(evaluate(args.models, args.text_only))
    if results[0].recall_at_5 < args.min_text_recall:
        raise SystemExit(f"text recall@5 {results[0].recall_at_5} < {args.min_text_recall}")


if __name__ == "__main__":
    main()
