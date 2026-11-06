"""Roles a user can have inside an organization."""

from enum import StrEnum


class Role(StrEnum):
    # Each member is also a str: Role.ADMIN == "admin", so it maps straight to the DB and JSON.
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


# Nobody can be invited as owner: ownership is only given by an existing owner (stage 2, step 16).
INVITABLE_ROLES: frozenset[Role] = frozenset({Role.ADMIN, Role.MEMBER, Role.VIEWER})
