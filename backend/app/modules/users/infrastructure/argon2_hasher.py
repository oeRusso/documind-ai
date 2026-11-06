"""PasswordHasher with Argon2id (argon2-cffi), defaults from RFC 9106 (64 MiB, 3 passes)."""

import asyncio

from argon2 import PasswordHasher as _Argon2
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class Argon2PasswordHasher:
    def __init__(self, hasher: _Argon2 | None = None) -> None:
        self._hasher = hasher or _Argon2()

    async def hash(self, password: str) -> str:
        # to_thread: Argon2 blocks the CPU on purpose; in a thread it does not freeze the API.
        return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        try:
            return await asyncio.to_thread(self._hasher.verify, password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
