"""The worker process (Celery). Composition root, like main.py is for the API.

celery -A app.worker worker --concurrency=1 --beat --loglevel=INFO
"""

# Register every SQLAlchemy model: the chunks table points to documents and organizations, and
# SQLAlchemy needs to know those tables to resolve the foreign keys (the API gets them by
# importing all routers; the worker imports only what it uses).
import app.infrastructure.database.models  # noqa: F401
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.infrastructure.queue.celery_app import create_celery
from app.modules.ingestion.presentation.tasks import register_tasks

settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
if not settings.celery_broker_url:
    raise RuntimeError("CELERY_BROKER_URL is required to run the worker")

celery = create_celery(settings.celery_broker_url)
register_tasks(celery, settings)
