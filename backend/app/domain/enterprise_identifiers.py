"""Deterministic, tenant-scoped enterprise identifier builders.

Identifiers are stable functions of the tenant and a natural key so that seeds
and imports are idempotent (the same logical entity always resolves to the same
id). These are domain identifiers and must never be produced by an LLM.
"""

from __future__ import annotations

import hashlib

_ID_LENGTH = 20


def _slugify(value: str) -> str:
    cleaned = []
    for char in value.strip().lower():
        if char.isalnum():
            cleaned.append(char)
        elif char in {" ", "-", "_", "/"}:
            cleaned.append("-")
    slug = "".join(cleaned)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def slugify(value: str) -> str:
    """Public deterministic slug helper (bounded, lowercase, hyphenated)."""
    return _slugify(value)[:64]


def build_entity_id(prefix: str, tenant_id: str, *natural_key: str) -> str:
    """Build a stable ``prefix_<hash>`` identifier for a tenant-scoped entity.

    The hash is derived from the tenant id and the natural key parts, so the
    identifier is unique within and across tenants while remaining reproducible.
    """
    parts = [tenant_id.strip().lower(), *[part.strip().lower() for part in natural_key]]
    canonical = "|".join(parts)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:_ID_LENGTH]
    return f"{prefix}_{digest}"
