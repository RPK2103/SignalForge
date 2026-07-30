"""Mandatory PostgreSQL RLS integration tests (Phase 3 Prompt 7).

These run only when ``POSTGRES_TEST_URL`` is provided (locally deferred when it
is absent) but are mandatory in GitHub Actions via a PostgreSQL service
container using a non-superuser application role. They are never silently
skipped in CI: the workflow always sets ``POSTGRES_TEST_URL``.
"""
