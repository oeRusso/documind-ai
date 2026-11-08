"""HTTP request/response shapes for auth. Format checks only; the rules live in `domain`."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InvitationAccept(BaseModel):
    """The two values in the invitation link, after `#`."""

    organization_id: UUID
    token: str = Field(min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    """Either `organization_name` + `organization_slug` (new organization) or `invitation`."""

    email: str = Field(max_length=254, examples=["ana@acme.com"])
    password: str = Field(max_length=128, examples=["una frase larga y fácil de recordar"])
    organization_name: str | None = Field(
        default=None, min_length=1, max_length=200, examples=["Acme S.A."]
    )
    organization_slug: str | None = Field(
        default=None, min_length=2, max_length=63, examples=["acme"]
    )
    invitation: InvitationAccept | None = None
    # Honeypot (ADR 0005): the web form hides this field, so people leave it empty and bots
    # that fill every input do not. Named like a normal field on purpose.
    website: str | None = Field(default=None, max_length=200, description="Dejar vacío")

    @model_validator(mode="after")
    def _organization_or_invitation(self) -> "RegisterRequest":
        creates = self.organization_name is not None or self.organization_slug is not None
        complete = self.organization_name is not None and self.organization_slug is not None
        if self.invitation is not None and creates:
            raise ValueError("Mandá la invitación o los datos de una organización nueva, no ambos")
        if self.invitation is None and not complete:
            raise ValueError("Faltan organization_name y organization_slug (o una invitación)")
        return self


class LoginRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class TokenResponse(BaseModel):
    """The refresh token is NOT here: it travels in an HttpOnly cookie."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 constant, not a secret
    expires_at: datetime


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
