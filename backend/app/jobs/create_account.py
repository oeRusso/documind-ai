"""Create an account with its own organization (as owner), for servers with closed sign-up.

    docker compose -f compose.prod.yaml exec api python -m app.jobs.create_account \\
        esteban@ejemplo.com "Mi Empresa" mi-empresa

The password is asked twice and never shown nor logged. With REGISTRATION_OPEN=false this is how
the first owner gets in; everyone else is invited from the web (Invitaciones).
"""

import argparse
import asyncio
import getpass
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
from app.modules.organizations.infrastructure.sql_repository import (
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from app.modules.users.application.create_user import CreateUser, CreateUserCommand
from app.modules.users.infrastructure.argon2_hasher import Argon2PasswordHasher
from app.modules.users.infrastructure.sql_repository import SqlUserRepository
from app.shared.errors import DomainError


async def create_account(
    settings: Settings, email: str, password: str, organization: str, slug: str
) -> None:
    engine = create_engine(str(settings.database_url))
    try:
        async with create_session_factory(engine)() as session, session.begin():
            users = SqlUserRepository(session)
            user = await CreateUser(users, Argon2PasswordHasher()).execute(
                CreateUserCommand(email, password)
            )
            tenant = SqlTenantContext(session)
            await tenant.set_user(user.id)
            await CreateOrganization(
                SqlOrganizationRepository(session),
                SqlMembershipRepository(session),
                tenant,
                RecordAuditEvent(SqlAuditLogRepository(session)),
            ).execute(CreateOrganizationCommand(name=organization, slug=slug, owner_id=user.id))
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("email")
    parser.add_argument("organization", help="nombre de la organización")
    parser.add_argument("slug", help="identificador corto: letras, números y guiones")
    args = parser.parse_args()
    password = getpass.getpass("Contraseña (10 caracteres o más): ")
    if password != getpass.getpass("Repetila: "):
        sys.exit("Las contraseñas no coinciden.")
    try:
        asyncio.run(
            create_account(get_settings(), args.email, password, args.organization, args.slug)
        )
    except DomainError as exc:
        sys.exit(f"No se pudo crear: {exc.message}")
    print(f"Listo: {args.email} es owner de «{args.organization}». Ya puede entrar en la web.")


if __name__ == "__main__":
    main()
