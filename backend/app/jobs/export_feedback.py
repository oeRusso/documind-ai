"""List the answers rated "no útil" of one organization, to grow the evaluation dataset.

    podman compose exec api python -m app.jobs.export_feedback <organization_id> \
        > backend/evaluation/feedback/<fecha>.json

Prints JSON: each question, the answer it got and what it cited. A person reviews them and,
for the ones worth it, adds a question to evaluation/questions.json with the document, the
article and the anchor that SHOULD have been found (stage 8: "las marcadas como no útiles
alimentan el dataset"). Nothing is added automatically: a wrong answer is not a right label.
Uses the `app` role inside the organization (RLS applies).
"""

import argparse
import asyncio
import json
import sys
from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.conversations.application.manage_conversations import (
    FeedbackCandidate,
    ListNotHelpfulAnswers,
)
from app.modules.conversations.infrastructure.sql_repository import SqlConversationRepository


def to_json(candidate: FeedbackCandidate) -> dict[str, Any]:
    return {
        "question": candidate.question.content,
        "answer": candidate.answer.content,
        "no_evidence": candidate.answer.no_evidence,
        "asked_at": candidate.question.created_at.isoformat(),
        "cited": [
            {
                "document": c.document_title,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "excerpt": c.excerpt,
            }
            for c in candidate.answer.citations
        ],
        # To fill by hand before moving it to questions.json:
        "expected": {"document": None, "article": None, "anchor": None},
    }


async def export(organization_id: UUID, limit: int) -> list[dict[str, Any]]:
    engine = create_engine(str(get_settings().database_url))
    try:
        async with create_session_factory(engine)() as session, session.begin():
            await SqlTenantContext(session).set_organization(organization_id)
            candidates = await ListNotHelpfulAnswers(SqlConversationRepository(session)).execute(
                organization_id, limit=limit
            )
    finally:
        await engine.dispose()
    return [to_json(c) for c in candidates]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("organization_id", type=UUID)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()
    items = asyncio.run(export(args.organization_id, args.limit))
    json.dump({"items": items}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
