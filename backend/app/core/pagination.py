"""List responses: `{ "items": [...], "next_cursor": "..." }` (CLAUDE.md, API conventions)."""

from pydantic import BaseModel


class Page[T](BaseModel):
    items: list[T]
    # None means there is nothing after this page.
    next_cursor: str | None = None
