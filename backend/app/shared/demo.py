"""The public demo (stage 12): fixed identifiers, so every part of the app can recognize it
without asking the database, and the nightly reset (app/jobs/reset_demo.py) always rebuilds the
same organization and accounts.

- DEMO_USER: the shared read-only account (viewer) whose password is public (DEMO_PASSWORD).
- DEMO_OWNER: a hidden owner that "uploads" the example documents; nobody can log in with it
  (its password is random and never stored).
The demo exists only when DEMO_PASSWORD is set.
"""

from uuid import UUID, uuid5

_NAMESPACE = UUID("6f6b3b8e-6a4c-4c55-9a3b-1d2f6c0de000")

DEMO_ORGANIZATION_ID = uuid5(_NAMESPACE, "organization")
DEMO_USER_ID = uuid5(_NAMESPACE, "viewer")
DEMO_OWNER_ID = uuid5(_NAMESPACE, "owner")
DEMO_SLUG = "demo-publica"  # reserved: nobody else can register it (CreateOrganization)
DEMO_NAME = "Demo · Leyes argentinas"
DEMO_EMAIL = "demo@documind.example"
DEMO_OWNER_EMAIL = "demo-owner@documind.example"
