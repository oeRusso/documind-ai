"""Measure how follow-up questions are searched (stage 8): which text goes to the search.

    uv run python -m evaluation.eval_followups

Two sets, both in hybrid mode with bge-m3 (the app's search), against the stage 6 corpus:
- follow-ups (evaluation/followups.json): "¿Y cuándo es válida?" after "¿Qué es la firma
  digital?". Alone they do not say what they are about: the previous question must help.
- topic changes: each answerable natural question of questions.json asked right after a
  question about ANOTHER law. Here the previous question can only get in the way.

Each strategy of app/modules/knowledge/domain/followup.py (and several "short" limits) is
measured with recall@5 and MRR on both sets. The report goes to docs/evaluation/.
Uses the TEST database and the PC's Ollama (OLLAMA_URL, default http://127.0.0.1:11434).
"""

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.ai.evaluation.metrics import first_relevant_rank, mean_reciprocal_rank, recall_at_k
from app.ai.providers.embeddings import embedding_model
from app.ai.providers.ollama import OllamaEmbeddingProvider
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.knowledge.application.search_documents import SearchDocuments, SearchQuery
from app.modules.knowledge.domain.followup import FollowupStrategy, followup_search_text
from app.modules.knowledge.domain.search import SearchMode
from app.modules.knowledge.infrastructure.sql_search import SqlChunkSearch
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.shared.ids import new_id, utc_now
from evaluation.dataset import Question, load_questions
from evaluation.eval_retrieval import (
    BACKEND,
    HERE,
    REPORTS,
    Corpus,
    create_organization,
    delete_organization,
    load_corpus,
    test_database_urls,
)

FOLLOWUPS = HERE / "followups.json"
RESULTS = HERE / "results" / "followups.json"
SHORT_LIMITS = (4, 6, 8, 10, 12)


@dataclass(frozen=True)
class Case:
    id: str
    previous: str  # the previous question's text
    question: str
    target: Question  # where the answer is (document and page)


@dataclass
class StrategyResult:
    name: str
    followups_recall_at_5: float
    followups_mrr: float
    topic_change_recall_at_5: float
    topic_change_mrr: float
    followup_misses: list[str]


def followup_cases(questions: dict[str, Question]) -> list[Case]:
    data = json.loads(FOLLOWUPS.read_text())["followups"]
    return [
        Case(f["id"], questions[f["previous"]].question, f["question"], questions[f["target"]])
        for f in data
    ]


def topic_change_cases(questions: list[Question]) -> list[Case]:
    """Each answerable natural question after the first natural question of another law."""
    natural = [q for q in questions if q.answerable and q.kind == "natural"]
    first_by_document: dict[str, Question] = {}
    for q in natural:
        first_by_document.setdefault(q.document or "", q)
    documents = list(first_by_document)
    cases = []
    for q in natural:
        other = documents[(documents.index(q.document or "") + 1) % len(documents)]
        cases.append(Case(q.id, first_by_document[other].question, q.question, q))
    return cases


async def ranks_for(
    engine: AsyncEngine,
    corpus: Corpus,
    provider: OllamaEmbeddingProvider,
    actor: Membership,
    cases: list[Case],
    text_for: "TextFor",
) -> list[int | None]:
    ranks = []
    for case in cases:
        async with AsyncSession(engine) as session, session.begin():
            await SqlTenantContext(session).set_organization(corpus.organization_id)
            result = await SearchDocuments(SqlChunkSearch(session), provider).execute(
                SearchQuery(
                    actor,
                    text_for(case.question, case.previous),
                    mode=SearchMode.HYBRID,
                    limit=10,
                )
            )
        expected = corpus.document_ids[case.target.document or ""]
        page = case.target.expected_page or 0
        ranks.append(
            first_relevant_rank(
                [
                    hit.match.document_id == expected
                    and hit.match.page_start is not None
                    and hit.match.page_start <= page <= (hit.match.page_end or 0)
                    for hit in result.hits
                ]
            )
        )
    return ranks


class TextFor:
    def __init__(self, strategy: FollowupStrategy, short_words: int = 6) -> None:
        self.strategy = strategy
        self.short_words = short_words

    @property
    def name(self) -> str:
        if self.strategy is FollowupStrategy.SHORT:
            return f"short (≤{self.short_words} palabras)"
        return self.strategy.value

    def __call__(self, question: str, previous: str) -> str:
        return followup_search_text(question, previous, self.strategy, short_words=self.short_words)


def write_report(results: list[StrategyResult], followups: int, changes: int) -> Path:
    today = datetime.now(UTC).date().isoformat()
    lines = [
        f"# Preguntas de seguimiento — {today}",
        "",
        "Generado por `uv run python -m evaluation.eval_followups` (etapa 8). No editar a mano.",
        "",
        "Qué texto se busca cuando hay una pregunta anterior en la conversación. Búsqueda híbrida "
        "con `bge-m3`, el mismo corpus de la etapa 6.",
        "",
        f"- **Seguimiento** ({followups} preguntas, `evaluation/followups.json`): «¿Y cuándo es "
        "válida?» después de «¿Qué es la firma digital?». Solas no dicen de qué hablan.",
        f"- **Cambio de tema** ({changes} preguntas): cada pregunta natural del dataset, hecha "
        "después de una pregunta sobre otra ley. Ahí la pregunta anterior solo puede estorbar.",
        "",
        "| Estrategia | seguimiento recall@5 | seguimiento MRR | cambio de tema recall@5 "
        "| cambio de tema MRR |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.name} | {r.followups_recall_at_5:.3f} | {r.followups_mrr:.3f} "
            f"| {r.topic_change_recall_at_5:.3f} | {r.topic_change_mrr:.3f} |"
        )
    lines += ["", "Preguntas de seguimiento fuera del top 5:", ""]
    for r in results:
        lines.append(f"- **{r.name}**: {', '.join(r.followup_misses) or 'ninguna'}")
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"followups-{today}.md"
    path.write_text("\n".join(lines) + "\n")
    return path


async def evaluate() -> list[StrategyResult]:
    app_url, migrator_url = test_database_urls()
    config = Config(str(BACKEND / "alembic.ini"))
    config.attributes["url"] = migrator_url
    await asyncio.to_thread(command.upgrade, config, "head")

    ollama = os.environ.get("OLLAMA_URL") or "http://127.0.0.1:11434"
    provider = OllamaEmbeddingProvider(ollama, embedding_model("bge-m3"), batch_size=32)
    engine = create_async_engine(app_url, poolclass=NullPool)
    migrator = create_async_engine(migrator_url, poolclass=NullPool)
    organization_id = await create_organization(migrator)
    try:
        print("Cargando el corpus…")
        corpus = await load_corpus(engine, organization_id, [provider])
        questions = load_questions()
        followups = followup_cases({q.id: q for q in questions})
        changes = topic_change_cases(questions)
        await provider.embed_query("calentamiento")
        actor = Membership.create(
            id=new_id(),
            organization_id=organization_id,
            user_id=new_id(),
            role=Role.VIEWER,
            now=utc_now(),
        )
        strategies = [TextFor(FollowupStrategy.NONE), TextFor(FollowupStrategy.ALWAYS)] + [
            TextFor(FollowupStrategy.SHORT, n) for n in SHORT_LIMITS
        ]
        results = []
        for text_for in strategies:
            f_ranks = await ranks_for(engine, corpus, provider, actor, followups, text_for)
            c_ranks = await ranks_for(engine, corpus, provider, actor, changes, text_for)
            result = StrategyResult(
                name=text_for.name,
                followups_recall_at_5=round(recall_at_k(f_ranks, 5), 3),
                followups_mrr=round(mean_reciprocal_rank(f_ranks), 3),
                topic_change_recall_at_5=round(recall_at_k(c_ranks, 5), 3),
                topic_change_mrr=round(mean_reciprocal_rank(c_ranks), 3),
                followup_misses=[
                    c.id for c, r in zip(followups, f_ranks, strict=True) if r is None or r > 5
                ],
            )
            results.append(result)
            print(
                f"{result.name:22} seguimiento r@5={result.followups_recall_at_5:.3f} "
                f"MRR={result.followups_mrr:.3f} | cambio de tema "
                f"r@5={result.topic_change_recall_at_5:.3f} MRR={result.topic_change_mrr:.3f}"
            )
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(
            json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2) + "\n"
        )
        print("Informe:", write_report(results, len(followups), len(changes)))
        return results
    finally:
        await delete_organization(migrator, organization_id)
        await engine.dispose()
        await migrator.dispose()


def main() -> None:
    asyncio.run(evaluate())


if __name__ == "__main__":
    main()
