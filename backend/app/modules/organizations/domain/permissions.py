"""Who can do what inside an organization. Pure functions, used by every use case.

Two kinds of rules:
1. Permissions per role (a table): "can an admin invite people?"
2. Rules between two people: "can this admin change that member's role?" An actor can only
   manage roles strictly below their own, except owners, who manage everyone.
"""

from enum import StrEnum

from app.modules.organizations.domain.errors import LastOwnerError, PermissionDeniedError
from app.modules.organizations.domain.roles import INVITABLE_ROLES, Role


class Permission(StrEnum):
    VIEW_MEMBERS = "members.view"
    INVITE_MEMBERS = "members.invite"
    MANAGE_MEMBERS = "members.manage"  # change roles, remove members
    MANAGE_ORGANIZATION = "organization.manage"  # rename, delete
    VIEW_AUDIT_LOG = "audit.view"


_GRANTS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.VIEW_MEMBERS,
            Permission.INVITE_MEMBERS,
            Permission.MANAGE_MEMBERS,
            Permission.VIEW_AUDIT_LOG,
        }
    ),
    Role.MEMBER: frozenset({Permission.VIEW_MEMBERS}),
    Role.VIEWER: frozenset({Permission.VIEW_MEMBERS}),
}

_RANK: dict[Role, int] = {Role.VIEWER: 0, Role.MEMBER: 1, Role.ADMIN: 2, Role.OWNER: 3}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in _GRANTS[role]


def ensure_permission(role: Role, permission: Permission) -> None:
    if not has_permission(role, permission):
        raise PermissionDeniedError()


def can_manage(actor: Role, target: Role) -> bool:
    """Can `actor` change the role of, or remove, someone who currently has `target`?"""
    if not has_permission(actor, Permission.MANAGE_MEMBERS):
        return False
    return actor is Role.OWNER or _RANK[target] < _RANK[actor]


def can_grant(actor: Role, role: Role) -> bool:
    """Can `actor` give `role` to someone (by changing their role or inviting them)?"""
    if not has_permission(actor, Permission.MANAGE_MEMBERS):
        return False
    return actor is Role.OWNER or _RANK[role] < _RANK[actor]


def can_invite_as(actor: Role, role: Role) -> bool:
    return (
        has_permission(actor, Permission.INVITE_MEMBERS)
        and role in INVITABLE_ROLES
        and can_grant(actor, role)
    )


def ensure_an_owner_remains(*, owner_count: int, target: Role, new_role: Role | None) -> None:
    """Block removing or demoting the last owner. `new_role=None` means removal."""
    if target is Role.OWNER and new_role is not Role.OWNER and owner_count <= 1:
        raise LastOwnerError()
