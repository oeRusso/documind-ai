"""Port for password hashing. The Argon2id implementation is in infrastructure."""

from typing import Protocol


class PasswordHasher(Protocol):
    # Async because hashing is deliberately slow (~50-100 ms of CPU): the implementation runs
    # it in a thread so the API keeps serving other requests meanwhile.
    async def hash(self, password: str) -> str: ...

    async def verify(self, password_hash: str, password: str) -> bool:
        """True if it matches. Never raises for a wrong password or a malformed hash."""
        ...
