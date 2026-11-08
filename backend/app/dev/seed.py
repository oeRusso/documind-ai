"""Load demo data to try the API by hand. Development only.

    podman compose exec api python -m app.dev.seed

Creates two organizations and five users, all with the same public password (DEMO_PASSWORD):
  Acme   -> ana (owner), carla (admin), mario (member), bob (viewer)
  Globex -> eve (owner)
Running it again does nothing if the data is already there.
"""

import asyncio
import sys

from app.core.config import Settings, get_settings
from app.infrastructure.database.session import create_engine, create_session_factory
from app.infrastructure.database.tenant import SqlTenantContext
from app.modules.audit.application.record_audit_event import RecordAuditEvent
from app.modules.audit.infrastructure.sql_repository import SqlAuditLogRepository
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
from app.shared.ids import new_id, utc_now

# Public on purpose: demo data in a local database. The script refuses to run outside development.
DEMO_PASSWORD = "documind-demo-2026"  # noqa: S105  # pragma: allowlist secret

ORGANIZATIONS = {
    "acme": ("Acme S.A.", "ana@acme.test"),
    "globex": ("Globex", "eve@globex.test"),
}
MEMBERS = {
    "acme": [
        ("carla@acme.test", Role.ADMIN),
        ("mario@acme.test", Role.MEMBER),
        ("bob@acme.test", Role.VIEWER),
    ],
}


async def seed(settings: Settings) -> bool:
    """Returns False if the demo data was already loaded."""
    engine = create_engine(str(settings.database_url))
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session, session.begin():
            users = SqlUserRepository(session)
            if await users.get_by_email("ana@acme.test") is not None:
                return False
            create_user = CreateUser(users, Argon2PasswordHasher())
            tenant = SqlTenantContext(session)
            memberships = SqlMembershipRepository(session)
            create_organization = CreateOrganization(
                SqlOrganizationRepository(session),
                memberships,
                tenant,
                RecordAuditEvent(SqlAuditLogRepository(session)),
            )
            for slug, (name, owner_email) in ORGANIZATIONS.items():
                owner = await create_user.execute(CreateUserCommand(owner_email, DEMO_PASSWORD))
                organization = await create_organization.execute(
                    CreateOrganizationCommand(name=name, slug=slug, owner_id=owner.id)
                )
                for email, role in MEMBERS.get(slug, []):
                    user = await create_user.execute(CreateUserCommand(email, DEMO_PASSWORD))
                    await memberships.add(
                        Membership.create(
                            id=new_id(),
                            organization_id=organization.id,
                            user_id=user.id,
                            role=role,
                            now=utc_now(),
                        )
                    )
        return True
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    if settings.app_env != "development":
        sys.exit("app.dev.seed only runs with APP_ENV=development")
    created = asyncio.run(seed(settings))
    print("Datos de prueba cargados." if created else "Los datos de prueba ya estaban cargados.")
    print(f"Contraseña de todos los usuarios: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
