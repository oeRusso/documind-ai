"""The permission matrix and the rules between two people (stage 2, criterion: viewer -> 403)."""

import pytest

from app.modules.organizations.domain.errors import LastOwnerError, PermissionDeniedError
from app.modules.organizations.domain.permissions import (
    Permission,
    can_grant,
    can_invite_as,
    can_manage,
    ensure_an_owner_remains,
    ensure_permission,
    has_permission,
)
from app.modules.organizations.domain.roles import Role

OWN, ADM, MEM, VIE = Role.OWNER, Role.ADMIN, Role.MEMBER, Role.VIEWER

# Expected matrix, written out on purpose: changing a permission must change this table.
EXPECTED: dict[Permission, set[Role]] = {
    Permission.VIEW_MEMBERS: {OWN, ADM, MEM, VIE},
    Permission.INVITE_MEMBERS: {OWN, ADM},
    Permission.MANAGE_MEMBERS: {OWN, ADM},
    Permission.MANAGE_ORGANIZATION: {OWN},
    Permission.VIEW_AUDIT_LOG: {OWN, ADM},
    Permission.VIEW_DOCUMENTS: {OWN, ADM, MEM, VIE},
    Permission.UPLOAD_DOCUMENTS: {OWN, ADM, MEM},
    Permission.DELETE_ANY_DOCUMENT: {OWN, ADM},
}


@pytest.mark.parametrize("permission", list(Permission))
@pytest.mark.parametrize("role", list(Role))
def test_permission_matrix(role: Role, permission: Permission) -> None:
    assert has_permission(role, permission) is (role in EXPECTED[permission])


def test_every_permission_is_in_the_expected_table() -> None:
    assert set(EXPECTED) == set(Permission)


def test_viewer_is_denied_admin_actions() -> None:
    for permission in (Permission.INVITE_MEMBERS, Permission.MANAGE_MEMBERS):
        with pytest.raises(PermissionDeniedError):
            ensure_permission(VIE, permission)


# (actor, target): can the actor change the role of, or remove, the target?
@pytest.mark.parametrize(
    ("actor", "target", "allowed"),
    [
        (OWN, OWN, True),  # owners manage everyone, other owners included
        (OWN, ADM, True),
        (OWN, VIE, True),
        (ADM, OWN, False),  # an admin never touches an owner
        (ADM, ADM, False),  # ...nor another admin
        (ADM, MEM, True),
        (ADM, VIE, True),
        (MEM, VIE, False),  # members and viewers manage nobody
        (VIE, VIE, False),
    ],
)
def test_can_manage(actor: Role, target: Role, allowed: bool) -> None:
    assert can_manage(actor, target) is allowed


@pytest.mark.parametrize(
    ("actor", "role", "allowed"),
    [
        (OWN, OWN, True),
        (OWN, ADM, True),
        (ADM, ADM, False),
        (ADM, MEM, True),
        (ADM, VIE, True),
        (MEM, VIE, False),
    ],
)
def test_can_grant(actor: Role, role: Role, allowed: bool) -> None:
    assert can_grant(actor, role) is allowed


@pytest.mark.parametrize(
    ("actor", "role", "allowed"),
    [
        (OWN, OWN, False),  # nobody is invited as owner
        (OWN, ADM, True),
        (ADM, ADM, False),
        (ADM, MEM, True),
        (ADM, VIE, True),
        (MEM, VIE, False),
        (VIE, VIE, False),
    ],
)
def test_can_invite_as(actor: Role, role: Role, allowed: bool) -> None:
    assert can_invite_as(actor, role) is allowed


@pytest.mark.parametrize("new_role", [None, ADM, MEM, VIE])
def test_last_owner_cannot_be_removed_or_demoted(new_role: Role | None) -> None:
    with pytest.raises(LastOwnerError):
        ensure_an_owner_remains(owner_count=1, target=OWN, new_role=new_role)


def test_an_owner_can_leave_when_another_remains() -> None:
    ensure_an_owner_remains(owner_count=2, target=OWN, new_role=None)


def test_non_owners_are_not_affected_by_the_owner_rule() -> None:
    ensure_an_owner_remains(owner_count=1, target=ADM, new_role=None)
