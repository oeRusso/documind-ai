"""Organization and membership repositories implemented with SQLAlchemy (PostgreSQL)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import (
    InvitationAlreadyPendingError,
    OrganizationSlugTakenError,
)
from app.modules.organizations.domain.invitation import Invitation
from app.modules.organizations.domain.membership import Membership
from app.modules.organizations.domain.roles import Role
from app.modules.organizations.infrastructure.models import (
    InvitationModel,
    MembershipModel,
    OrganizationModel,
)


def _to_entity(model: OrganizationModel) -> Organization:
    return Organization(
        id=model.id,
        name=model.name,
        slug=model.slug,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlOrganizationRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, organization: Organization) -> None:
        self._session.add(
            OrganizationModel(
                id=organization.id,
                name=organization.name,
                slug=organization.slug,
                created_at=organization.created_at,
                updated_at=organization.updated_at,
            )
        )
        try:
            await self._session.flush()  # sends the INSERT now, so constraint errors surface here
        except IntegrityError as exc:
            raise OrganizationSlugTakenError() from exc

    async def get_by_id(self, organization_id: UUID) -> Organization | None:
        model = await self._session.get(OrganizationModel, organization_id)
        return _to_entity(model) if model else None


def _membership_to_entity(model: MembershipModel) -> Membership:
    return Membership(
        id=model.id,
        organization_id=model.organization_id,
        user_id=model.user_id,
        role=Role(model.role),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlMembershipRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, membership: Membership) -> None:
        self._session.add(
            MembershipModel(
                id=membership.id,
                organization_id=membership.organization_id,
                user_id=membership.user_id,
                role=str(membership.role),
                created_at=membership.created_at,
                updated_at=membership.updated_at,
            )
        )
        await self._session.flush()

    async def get_by_user(self, organization_id: UUID, user_id: UUID) -> Membership | None:
        result = await self._session.execute(
            select(MembershipModel).where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.user_id == user_id,
            )
        )
        model = result.scalar_one_or_none()
        return _membership_to_entity(model) if model else None

    async def list_by_user(self, user_id: UUID) -> list[Membership]:
        result = await self._session.execute(
            select(MembershipModel)
            .where(MembershipModel.user_id == user_id)
            .order_by(MembershipModel.created_at)
        )
        return [_membership_to_entity(model) for model in result.scalars()]

    async def list_for_organization(self, organization_id: UUID) -> list[Membership]:
        result = await self._session.execute(
            select(MembershipModel)
            .where(MembershipModel.organization_id == organization_id)
            .order_by(MembershipModel.created_at, MembershipModel.id)
        )
        return [_membership_to_entity(model) for model in result.scalars()]

    async def get_by_id(self, organization_id: UUID, membership_id: UUID) -> Membership | None:
        result = await self._session.execute(
            select(MembershipModel).where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.id == membership_id,
            )
        )
        model = result.scalar_one_or_none()
        return _membership_to_entity(model) if model else None

    async def count_owners_for_update(self, organization_id: UUID) -> int:
        # ORDER BY id: every transaction locks the rows in the same order, so two of them
        # cannot each hold one row while waiting for the other (a deadlock).
        result = await self._session.execute(
            select(MembershipModel.id)
            .where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.role == str(Role.OWNER),
            )
            .order_by(MembershipModel.id)
            .with_for_update()
        )
        return len(result.scalars().all())

    async def update_role(
        self, organization_id: UUID, membership_id: UUID, role: Role, now: datetime
    ) -> None:
        await self._session.execute(
            update(MembershipModel)
            .where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.id == membership_id,
            )
            .values(role=str(role), updated_at=now)
        )

    async def remove(self, organization_id: UUID, membership_id: UUID) -> None:
        await self._session.execute(
            delete(MembershipModel).where(
                MembershipModel.organization_id == organization_id,
                MembershipModel.id == membership_id,
            )
        )


def _invitation_to_entity(model: InvitationModel) -> Invitation:
    return Invitation(
        id=model.id,
        organization_id=model.organization_id,
        email=model.email,
        role=Role(model.role),
        token_hash=model.token_hash,
        invited_by_id=model.invited_by_id,
        expires_at=model.expires_at,
        accepted_at=model.accepted_at,
        revoked_at=model.revoked_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlInvitationRepository:
    """Does not commit: the transaction belongs to the request (see get_session)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, invitation: Invitation) -> None:
        self._session.add(
            InvitationModel(
                id=invitation.id,
                organization_id=invitation.organization_id,
                email=invitation.email,
                role=str(invitation.role),
                token_hash=invitation.token_hash,
                invited_by_id=invitation.invited_by_id,
                expires_at=invitation.expires_at,
                accepted_at=invitation.accepted_at,
                revoked_at=invitation.revoked_at,
                created_at=invitation.created_at,
                updated_at=invitation.updated_at,
            )
        )
        try:
            await self._session.flush()
        except IntegrityError as exc:  # uq_invitations_organization_id_email_open
            raise InvitationAlreadyPendingError() from exc

    @staticmethod
    def _open(organization_id: UUID) -> tuple[ColumnElement[bool], ...]:
        """WHERE conditions of an open invitation (not accepted, not revoked)."""
        return (
            InvitationModel.organization_id == organization_id,
            InvitationModel.accepted_at.is_(None),
            InvitationModel.revoked_at.is_(None),
        )

    async def list_open(self, organization_id: UUID) -> list[Invitation]:
        result = await self._session.execute(
            select(InvitationModel)
            .where(*self._open(organization_id))
            .order_by(InvitationModel.created_at, InvitationModel.id)
        )
        return [_invitation_to_entity(model) for model in result.scalars()]

    async def get_by_id(self, organization_id: UUID, invitation_id: UUID) -> Invitation | None:
        result = await self._session.execute(
            select(InvitationModel).where(
                InvitationModel.organization_id == organization_id,
                InvitationModel.id == invitation_id,
            )
        )
        model = result.scalar_one_or_none()
        return _invitation_to_entity(model) if model else None

    async def get_open_by_email(self, organization_id: UUID, email: str) -> Invitation | None:
        result = await self._session.execute(
            select(InvitationModel).where(
                *self._open(organization_id), InvitationModel.email == email
            )
        )
        model = result.scalar_one_or_none()
        return _invitation_to_entity(model) if model else None

    async def get_by_token_hash_for_update(
        self, organization_id: UUID, token_hash: str
    ) -> Invitation | None:
        result = await self._session.execute(
            select(InvitationModel)
            .where(
                InvitationModel.organization_id == organization_id,
                InvitationModel.token_hash == token_hash,
            )
            .with_for_update()
        )
        model = result.scalar_one_or_none()
        return _invitation_to_entity(model) if model else None

    async def save_status(self, invitation: Invitation) -> None:
        await self._session.execute(
            update(InvitationModel)
            .where(
                InvitationModel.organization_id == invitation.organization_id,
                InvitationModel.id == invitation.id,
            )
            .values(
                accepted_at=invitation.accepted_at,
                revoked_at=invitation.revoked_at,
                updated_at=invitation.updated_at,
            )
        )
