"""Identifier and clock helpers. Injected into use cases so tests can control them."""

from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


def new_id() -> UUID:
    """UUID v7: random but ordered by creation time (good for B-tree indexes). See ADR 0002."""
    return uuid7()


def utc_now() -> datetime:
    return datetime.now(UTC)
