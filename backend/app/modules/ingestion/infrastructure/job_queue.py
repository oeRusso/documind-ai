"""JobQueue implementations: Celery (Valkey) in the stack, and a no-op one without a broker."""

from uuid import UUID

import structlog
from celery import Celery

from app.infrastructure.queue.celery_app import DOCUMENTS_QUEUE, PROCESS_VERSION_TASK

logger = structlog.get_logger("app.ingestion")


class CeleryJobQueue:
    def __init__(self, celery: Celery) -> None:
        self._celery = celery

    def enqueue(self, organization_id: UUID, job_id: UUID) -> None:
        self._celery.send_task(
            PROCESS_VERSION_TASK,
            args=[str(organization_id), str(job_id)],
            queue=DOCUMENTS_QUEUE,
        )


class LoggingJobQueue:
    """Without CELERY_BROKER_URL nothing is processed: the job stays pending (and logged)."""

    def enqueue(self, organization_id: UUID, job_id: UUID) -> None:
        logger.info("job_not_sent_no_broker", job_id=str(job_id))
