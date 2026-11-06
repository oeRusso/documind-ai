"""HTTP request/response shapes (Pydantic). Validation of format only; rules live in domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.organizations.application.get_organization import OrganizationWithRole
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
