"""HTTP request/response shapes for auth. Format checks only; the rules live in `domain`."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    email: str = Field(max_length=254, examples=["ana@acme.com"])
    password: str = Field(max_length=128, examples=["una frase larga y fácil de recordar"])
    organization_name: str = Field(min_length=1, max_length=200, examples=["Acme S.A."])
    organization_slug: str = Field(min_length=2, max_length=63, examples=["acme"])


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
