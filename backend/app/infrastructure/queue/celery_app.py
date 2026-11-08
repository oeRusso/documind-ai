"""The Celery application: the API uses it to send tasks, the worker to run them.

Settings chosen for "never lose nor duplicate work" (stage 5) on a small shared server:
- acks_late + reject_on_worker_lost: a task is confirmed only after it finished. If the worker
  dies, Valkey hands the task out again (after `visibility_timeout`).
- prefetch 1 and concurrency 1 (in the worker command): one document at a time, so OCR does not
  starve the LLM of CPU and RAM.
- Results are not stored: the outcome lives in the processing_jobs table.
"""

from celery import Celery

PROCESS_VERSION_TASK = "ingestion.process_version"
PURGE_DOCUMENTS_TASK = "documents.purge_deleted"
DOCUMENTS_QUEUE = "documents"

# Hard limit per task and how long Valkey waits before handing out an unconfirmed task again.
TASK_TIME_LIMIT_SECONDS = 30 * 60
VISIBILITY_TIMEOUT_SECONDS = TASK_TIME_LIMIT_SECONDS + 5 * 60


def create_celery(broker_url: str) -> Celery:
    app = Celery("documind", broker=broker_url)
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_ignore_result=True,
        task_default_queue=DOCUMENTS_QUEUE,
        task_time_limit=TASK_TIME_LIMIT_SECONDS,
        task_soft_time_limit=TASK_TIME_LIMIT_SECONDS - 60,
        worker_prefetch_multiplier=1,
        worker_hijack_root_logger=False,
        broker_connection_retry_on_startup=True,
        broker_transport_options={"visibility_timeout": VISIBILITY_TIMEOUT_SECONDS},
        timezone="UTC",
        beat_schedule={
            "purge-deleted-documents": {
                "task": PURGE_DOCUMENTS_TASK,
                "schedule": 24 * 60 * 60,  # once a day
            }
        },
    )
    return app
