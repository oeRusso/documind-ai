"""Write the API's OpenAPI document to a file, without a database or real secrets.

    uv run python -m app.dev.openapi ../frontend/openapi.json

The frontend generates its TypeScript client from that file (pnpm gen:api). CI regenerates
it and fails if the committed copy is out of date.
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.main import create_app

# Placeholders: building the app creates the engine, but nothing connects to it.
_OFFLINE = {
    "app_env": "test",
    "database_url": "postgresql+asyncpg://localhost:5432/offline",
    "database_migration_url": "postgresql+asyncpg://localhost:5432/offline",
    "jwt_secret": "offline-openapi-export-" + "x" * 32,  # pragma: allowlist secret
}


def openapi_document() -> dict[str, Any]:
    settings = Settings.model_validate(_OFFLINE)
    document: dict[str, Any] = create_app(settings).openapi()
    return document


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m app.dev.openapi <output.json>")
    text = json.dumps(openapi_document(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    Path(sys.argv[1]).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
