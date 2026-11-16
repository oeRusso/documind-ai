"""Create or reset the public demo (stage 12). Runs every night (Celery beat) and by hand:

    podman compose exec api python -m app.jobs.reset_demo

What it leaves, always the same (fixed ids in app/shared/demo.py):
- organization "Demo · Leyes argentinas" with the example laws of app/demo_documents/,
  uploaded and processed by the normal pipeline (only the ones that are missing);
- the shared read-only account (viewer) with DEMO_PASSWORD;
- no conversations: every night the questions of the day are deleted (the account is shared).
Does nothing if DEMO_PASSWORD is not set.
"""

import asyncio
import hashlib
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.tenant import SqlTenantContext
from app.infrastructure.queue.celery_app import create_celery
from app.infrastructure.storage.filesystem import FilesystemStorage
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
from app.modules.conversations.infrastructure.sql_repository import SqlConversationRepository
from app.modules.documents.application.upload_document import (
    UploadDocument,
    UploadDocumentCommand,
)
from app.modules.documents.domain.entities import StagedUpload
from app.modules.documents.domain.errors import DuplicateDocumentError
from app.modules.documents.infrastructure.file_inspector import LibmagicFileInspector
from app.modules.documents.infrastructure.sql_repository import SqlDocumentRepository
from app.modules.ingestion.application.jobs import ScheduleProcessing
from app.modules.ingestion.infrastructure.job_queue import CeleryJobQueue
from app.modules.ingestion.infrastructure.sql_repository import SqlJobRepository
from app.modules.organizations.application.create_organization import (
    CreateOrganization,
    CreateOrganizationCommand,
)
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.modules.organizations.infrastructure.sql_repository import (
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from app.modules.users.application.create_user import CreateUser, CreateUserCommand
from app.modules.users.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.modules.users.infrastructure.sql_repository import SqlUserRepository
from app.shared.demo import (
    DEMO_EMAIL,
    DEMO_NAME,
    DEMO_ORGANIZATION_ID,
    DEMO_OWNER_EMAIL,
    DEMO_OWNER_ID,
    DEMO_SLUG,
    DEMO_USER_ID,
)
from app.shared.ids import new_id, utc_now

logger = structlog.get_logger("app.jobs.reset_demo")

DOCUMENTS_DIR = Path(__file__).parents[1] / "demo_documents"


@dataclass
class ResetReport:
    created: bool = False
    conversations_deleted: int = 0
    uploaded: list[str] = field(default_factory=list)
    jobs: list[tuple[UUID, UUID]] = field(default_factory=list)


class _CollectingQueue:
    """Remembers the jobs to send them AFTER the commit (a worker must see the rows)."""

    def __init__(self, report: ResetReport) -> None:
        self._report = report

    def enqueue(self, organization_id: UUID, job_id: UUID) -> None:
        self._report.jobs.append((organization_id, job_id))


def _stage(source: Path, staging_dir: Path) -> StagedUpload:
    staging_dir.mkdir(parents=True, exist_ok=True)
    target = staging_dir / secrets.token_hex(16)
    shutil.copyfile(source, target)
    data = target.read_bytes()
    return StagedUpload(
        path=target,
        filename=source.name,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


async def reset_demo(settings: Settings, *, send_jobs: bool = True) -> ResetReport | None:
    if settings.demo_password is None:
        return None
    password = settings.demo_password.get_secret_value()
    report = ResetReport()
    engine = create_engine(str(settings.database_url))
    storage = FilesystemStorage(settings.storage_path)
    try:
        async with create_session_factory(engine)() as session, session.begin():
            users = SqlUserRepository(session)
            hasher = Argon2PasswordHasher()
            viewer = await users.get_by_id(DEMO_USER_ID)
            if viewer is None:
                await CreateUser(users, hasher, id_factory=lambda: DEMO_USER_ID).execute(
                    CreateUserCommand(DEMO_EMAIL, password)
                )
            elif not await hasher.verify(viewer.password_hash, password):
                await users.set_password_hash(DEMO_USER_ID, await hasher.hash(password))
            if await users.get_by_id(DEMO_OWNER_ID) is None:
                # Nobody logs in as the owner: its password is random and forgotten at once.
                await CreateUser(users, hasher, id_factory=lambda: DEMO_OWNER_ID).execute(
                    CreateUserCommand(DEMO_OWNER_EMAIL, secrets.token_urlsafe(32))
                )

            tenant = SqlTenantContext(session)
            await tenant.set_organization(DEMO_ORGANIZATION_ID)
            organizations = SqlOrganizationRepository(session)
            memberships = SqlMembershipRepository(session)
            audit = RecordAuditEvent(SqlAuditLogRepository(session))
            if await organizations.get_by_id(DEMO_ORGANIZATION_ID) is None:
                create = CreateOrganization(
                    organizations,
                    memberships,
                    tenant,
                    audit,
                    id_factory=lambda: DEMO_ORGANIZATION_ID,
                )
                await create.execute(
                    CreateOrganizationCommand(
                        name=DEMO_NAME, slug=DEMO_SLUG, owner_id=DEMO_OWNER_ID
                    )
                )
                report.created = True
            if await memberships.get_by_user(DEMO_ORGANIZATION_ID, DEMO_USER_ID) is None:
                await memberships.add(
                    Membership.create(
                        id=new_id(),
                        organization_id=DEMO_ORGANIZATION_ID,
                        user_id=DEMO_USER_ID,
                        role=Role.VIEWER,
                        now=utc_now(),
                    )
                )
            owner = await memberships.get_by_user(DEMO_ORGANIZATION_ID, DEMO_OWNER_ID)
            if owner is None:  # created with the organization: something is very wrong
                raise RuntimeError("the demo organization has no owner")

            report.conversations_deleted = await SqlConversationRepository(session).delete_all(
                DEMO_ORGANIZATION_ID
            )
            upload = UploadDocument(
                SqlDocumentRepository(session),
                storage,
                LibmagicFileInspector(max_pages=settings.max_upload_pages),
                audit,
                ScheduleProcessing(SqlJobRepository(session), _CollectingQueue(report)),
            )
            for path in sorted(DOCUMENTS_DIR.glob("*.pdf")):
                staged = _stage(path, storage.staging_dir())
                try:
                    await upload.execute(UploadDocumentCommand(owner, staged))
                    report.uploaded.append(path.stem)
                except DuplicateDocumentError:
                    pass  # already there
                finally:
                    staged.path.unlink(missing_ok=True)
        if send_jobs and report.jobs and settings.celery_broker_url:
            queue = CeleryJobQueue(create_celery(settings.celery_broker_url))
            for organization_id, job_id in report.jobs:
                queue.enqueue(organization_id, job_id)
    finally:
        await engine.dispose()
    logger.info(
        "demo_reset",
        created=report.created,
        conversations_deleted=report.conversations_deleted,
        uploaded=report.uploaded,
    )
    return report


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    report = asyncio.run(reset_demo(settings))
    if report is None:
        print("La demo está apagada (DEMO_PASSWORD no está configurada).")
        return
    print(
        f"Demo lista: {len(report.uploaded)} documentos subidos, "
        f"{report.conversations_deleted} conversaciones borradas."
    )


if __name__ == "__main__":
    main()
