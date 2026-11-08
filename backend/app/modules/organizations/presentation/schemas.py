"""HTTP request/response shapes (Pydantic). Validation of format only; rules live in domain."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.organizations.application.get_organization import OrganizationWithRole
from app.modules.organizations.application.manage_members import MemberView
from app.modules.organizations.domain.invitation import Invitation, InvitationStatus
from app.modules.organizations.domain.roles import Role


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, examples=["Acme S.A."])
    slug: str = Field(min_length=2, max_length=63, examples=["acme"])


class OrganizationRead(BaseModel):
    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
    role: Role = Field(description="Tu rol en esta organización")

    @classmethod
    def build(cls, item: OrganizationWithRole) -> "OrganizationRead":
        org = item.organization
        return cls(
            id=org.id,
            name=org.name,
            slug=org.slug,
            created_at=org.created_at,
            updated_at=org.updated_at,
            role=item.role,
        )


class MemberRead(BaseModel):
    id: UUID = Field(description="Id de la membresía (se usa para cambiar el rol o quitarla)")
    user_id: UUID
    email: str
    role: Role
    created_at: datetime = Field(description="Desde cuándo es miembro")

    @classmethod
    def build(cls, item: MemberView) -> "MemberRead":
        return cls(
            id=item.membership.id,
            user_id=item.membership.user_id,
            email=item.email,
            role=item.membership.role,
            created_at=item.membership.created_at,
        )


class MemberRoleUpdate(BaseModel):
    role: Role


InvitableRole = Literal[Role.ADMIN, Role.MEMBER, Role.VIEWER]


class InvitationCreate(BaseModel):
    email: str = Field(max_length=254, examples=["carla@acme.com"])
    role: InvitableRole = Field(description="owner no se invita: se asigna a un miembro existente")


class InvitationRead(BaseModel):
    id: UUID
    email: str
    role: Role
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    invited_by_id: UUID | None

    @classmethod
    def build(cls, invitation: Invitation, now: datetime) -> "InvitationRead":
        return cls(
            id=invitation.id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status(now),
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            invited_by_id=invitation.invited_by_id,
        )


class CreatedInvitationRead(InvitationRead):
    link: str = Field(
        description="Link para aceptar. Se muestra **solo esta vez**: el token no se guarda."
    )
