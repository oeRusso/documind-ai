"""Row Level Security on organizations, memberships, invitations and audit_logs (ADR 0003).

The app sets two variables per transaction with set_config(..., true):
  app.current_user -> who is asking
  app.current_org  -> the active organization
Without them, these tables return no rows: a forgotten context fails closed.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("organizations", "memberships", "invitations", "audit_logs")


def upgrade() -> None:
    # Readable helpers for the policies. NULLIF matters: once a variable has been set on a
    # pooled connection, it comes back as '' (not NULL) in later transactions, and ''::uuid fails.
    op.execute("""
        CREATE FUNCTION current_org_id() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT NULLIF(current_setting('app.current_org', true), '')::uuid $$
    """)
    op.execute("""
        CREATE FUNCTION current_user_id() RETURNS uuid
        LANGUAGE sql STABLE
        AS $$ SELECT NULLIF(current_setting('app.current_user', true), '')::uuid $$
    """)

    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE: the table owner (migrator) is subject to the policies too.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # organizations: full access to the active one; read-only access to the ones I belong to
    # (the organization selector lists them before one is chosen).
    op.execute("""
        CREATE POLICY tenant_isolation ON organizations
        USING (id = current_org_id())
        WITH CHECK (id = current_org_id())
    """)
    op.execute("""
        CREATE POLICY member_can_read ON organizations FOR SELECT
        USING (EXISTS (
            SELECT 1 FROM memberships m
            WHERE m.organization_id = organizations.id AND m.user_id = current_user_id()
        ))
    """)

    # memberships: the active organization's, plus my own anywhere (read-only).
    # This policy must not query organizations: their policies would call each other forever.
    op.execute("""
        CREATE POLICY tenant_isolation ON memberships
        USING (organization_id = current_org_id())
        WITH CHECK (organization_id = current_org_id())
    """)
    op.execute("""
        CREATE POLICY own_memberships ON memberships FOR SELECT
        USING (user_id = current_user_id())
    """)

    # invitations: only the active organization's. Accepting one sets the organization that
    # comes in the link, so no bypass is needed.
    op.execute("""
        CREATE POLICY tenant_isolation ON invitations
        USING (organization_id = current_org_id())
        WITH CHECK (organization_id = current_org_id())
    """)

    # audit_logs: insert-only for the app. Events without an organization (a failed login)
    # can always be written; reading is limited to the active organization.
    op.execute("""
        CREATE POLICY insert_events ON audit_logs FOR INSERT
        WITH CHECK (organization_id IS NULL OR organization_id = current_org_id())
    """)
    op.execute("""
        CREATE POLICY read_own_organization ON audit_logs FOR SELECT
        USING (organization_id = current_org_id())
    """)
    op.execute("REVOKE UPDATE, DELETE, TRUNCATE ON audit_logs FROM app")


def downgrade() -> None:
    op.execute("GRANT UPDATE, DELETE ON audit_logs TO app")
    op.execute("DROP POLICY read_own_organization ON audit_logs")
    op.execute("DROP POLICY insert_events ON audit_logs")
    op.execute("DROP POLICY tenant_isolation ON invitations")
    op.execute("DROP POLICY own_memberships ON memberships")
    op.execute("DROP POLICY tenant_isolation ON memberships")
    op.execute("DROP POLICY member_can_read ON organizations")
    op.execute("DROP POLICY tenant_isolation ON organizations")
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION current_user_id()")
    op.execute("DROP FUNCTION current_org_id()")
