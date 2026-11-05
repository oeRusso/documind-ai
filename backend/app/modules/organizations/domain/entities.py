"""Organization entity: pure Python, no FastAPI, no SQLAlchemy."""

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.organizations.domain.errors import InvalidOrganizationError

NAME_MAX_LENGTH = 200
SLUG_MAX_LENGTH = 63
# Lowercase letters, digits and single hyphens; must start and end with a letter or digit.
SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9]|-(?=[a-z0-9])){1,62}$")


@dataclass(slots=True)
class Organization:
    id: UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, *, id: UUID, name: str, slug: str, now: datetime) -> "Organization":
        name = name.strip()
        slug = slug.strip().lower()
        if not name or len(name) > NAME_MAX_LENGTH:
            raise InvalidOrganizationError(
                f"El nombre debe tener entre 1 y {NAME_MAX_LENGTH} caracteres"
            )
        if not SLUG_PATTERN.fullmatch(slug):
            raise InvalidOrganizationError(
                "El slug solo admite minúsculas, números y guiones (2 a 63 caracteres)"
            )
        return cls(id=id, name=name, slug=slug, created_at=now, updated_at=now)
