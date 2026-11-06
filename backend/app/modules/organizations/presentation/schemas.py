"""HTTP request/response shapes (Pydantic). Validation of format only; rules live in domain."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200, examples=["Acme S.A."])
    slug: str = Field(min_length=2, max_length=63, examples=["acme"])


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime
