"""Use case: check an email and password. Returns the user or None, never which part failed."""

from app.modules.users.domain.entities import User, normalize_email
from app.modules.users.domain.errors import InvalidEmailError
from app.modules.users.domain.passwords import PasswordHasher
from app.modules.users.domain.repository import UserRepository

# Argon2id hash (same parameters as real ones) of a random string nobody knows. When the email
# does not exist we still verify against it, so the response takes as long as for a real
# account: the timing does not reveal which emails are registered.
_TIMING_EQUALIZER_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$6PJ6RT5r5eIC6kFFNzlbkg$"  # pragma: allowlist secret
    "WTQJGEB0VU2DBVULWStfHUeImpAsVLy+cCVvz6ChNVQ"  # pragma: allowlist secret
)


class VerifyCredentials:
    def __init__(self, repository: UserRepository, hasher: PasswordHasher) -> None:
        self._repository = repository
        self._hasher = hasher

    async def execute(self, email: str, password: str) -> User | None:
        try:
            user = await self._repository.get_by_email(normalize_email(email))
        except InvalidEmailError:
            user = None

        if user is None:
            await self._hasher.verify(_TIMING_EQUALIZER_HASH, password)
            return None
        if not await self._hasher.verify(user.password_hash, password):
            return None
        # Checked last, so a disabled account answers exactly like a wrong password.
        return user if user.is_active else None
