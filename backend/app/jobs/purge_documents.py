"""Remove the files of documents deleted more than DOCUMENT_PURGE_DAYS ago.

    python -m app.jobs.purge_documents

Meant to run once a day (cron in production, Celery beat from stage 5). Uses the API's
restricted `app` role: it never bypasses Row Level Security (see PurgeDeletedDocuments).
"""

import asyncio

import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.tenant import SqlTenantContext
from app.infrastructure.storage.filesystem import FilesystemStorage
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.documents.application.delete_document import PurgeDeletedDocuments
from app.modules.documents.infrastructure.sql_repository import (
    SqlDocumentRepository,
    SqlPurgeQueue,
)

logger = structlog.get_logger("app.jobs.purge_documents")


async def purge_all(batch_size: int = 200) -> int:
    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    sessions = create_session_factory(engine)
    storage = FilesystemStorage(settings.storage_path)
    total = 0
    try:
        while True:
            # One transaction per batch: a failure loses at most one batch, and it is retried.
            async with sessions() as session, session.begin():
                purged = await PurgeDeletedDocuments(
                    SqlPurgeQueue(session),
                    SqlDocumentRepository(session),
                    storage,
                    SqlTenantContext(session),
                    RecordAuditEvent(SqlAuditLogRepository(session)),
                ).execute(batch_size=batch_size)
            total += purged
            if purged < batch_size:
                return total
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    total = asyncio.run(purge_all())
    logger.info("documents_purged", files=total)


if __name__ == "__main__":
    main()
