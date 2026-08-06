"""NovaBank realistic enterprise demo dataset (Phase 3 Prompt 9).

All data is synthetic, deterministic and production-ineligible.
"""

from __future__ import annotations

from app.demo.novabank.constants import (
    AS_OF_AT,
    DATASET_NAME,
    DATASET_VERSION,
    GENERATOR_VERSION,
    TENANT_ID,
)
from app.demo.novabank.specification import CANONICAL_SPEC

__all__ = [
    "AS_OF_AT",
    "CANONICAL_SPEC",
    "DATASET_NAME",
    "DATASET_VERSION",
    "GENERATOR_VERSION",
    "TENANT_ID",
]
