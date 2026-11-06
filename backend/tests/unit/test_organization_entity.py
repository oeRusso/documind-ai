from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.organizations.domain.entities import Organization
from app.modules.organizations.domain.errors import InvalidOrganizationError

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
ORG_ID = UUID("0192f1c4-0000-7000-8000-000000000001")


def test_create_normalizes_name_and_slug() -> None:
    organization = Organization.create(id=ORG_ID, name="  Acme S.A.  ", slug=" ACME-ar ", now=NOW)

    assert organization.name == "Acme S.A."
    assert organization.slug == "acme-ar"
    assert organization.created_at == organization.updated_at == NOW


@pytest.mark.parametrize("slug", ["a", "-acme", "acme-", "ac--me", "acme corp", "ácme", "a" * 64])
def test_create_rejects_invalid_slug(slug: str) -> None:
    with pytest.raises(InvalidOrganizationError):
        Organization.create(id=ORG_ID, name="Acme", slug=slug, now=NOW)


@pytest.mark.parametrize("name", ["", "   ", "x" * 201])
def test_create_rejects_invalid_name(name: str) -> None:
    with pytest.raises(InvalidOrganizationError):
        Organization.create(id=ORG_ID, name=name, slug="acme", now=NOW)
