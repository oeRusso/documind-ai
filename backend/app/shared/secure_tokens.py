"""Random tokens for links and cookies (refresh tokens, invitations).

Only the SHA-256 hash is stored: a leaked database does not give working tokens.
A plain hash (no salt, no Argon2) is enough because the token has 256 random bits:
there is nothing to guess, unlike a human password.
"""

import hashlib
import secrets

TOKEN_BYTES = 32  # 256 bits


def generate_token() -> str:
    """URL-safe random token, ~43 characters."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """SHA-256 in hex (64 characters), the value stored in the database."""
    return hashlib.sha256(token.encode()).hexdigest()
