"""JobQueue for HTTP requests: jobs are sent after the response, so after the commit.

Sending before the commit would let a fast worker look for a job row that is not visible yet.
If sending fails (the queue is down), the job stays pending in the database and is sent again
the next time someone looks at the document (GetProcessingStatus).
"""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import BackgroundTasks, Depends, Request

from app.modules.ingestion.domain.ports import JobQueue

logger = structlog.get_logger(__name__)


class BackgroundJobQueue:
    def __init__(self, background_tasks: BackgroundTasks, queue: JobQueue) -> None:
        self._background_tasks = background_tasks
        self._queue = queue

    def enqueue(self, organization_id: UUID, job_id: UUID) -> None:
        self._background_tasks.add_task(self._send, organization_id, job_id)

    def _send(self, organization_id: UUID, job_id: UUID) -> None:
        try:
            self._queue.enqueue(organization_id, job_id)
        except Exception as exc:
            logger.warning("job_send_failed", job_id=str(job_id), error=type(exc).__name__)


def get_job_queue(request: Request, background_tasks: BackgroundTasks) -> BackgroundJobQueue:
    return BackgroundJobQueue(background_tasks, request.app.state.job_queue)


JobQueueDep = Annotated[BackgroundJobQueue, Depends(get_job_queue)]
