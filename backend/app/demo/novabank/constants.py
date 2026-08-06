"""Versioned constants for the NovaBank enterprise demo dataset."""

from __future__ import annotations

from datetime import datetime, timezone

DATASET_NAME = "novabank-enterprise-demo"
DATASET_VERSION = "novabank-enterprise-demo-v2"
GENERATOR_VERSION = "novabank-generator-v1"
SCHEMA_COMPAT = "p3_observability_ai_quality"
TENANT_ID = "novabank"

# Canonical temporal anchor for Prompt 9. Observed evidence must not exceed this.
AS_OF_AT = datetime(2026, 7, 31, 18, 0, 0, tzinfo=timezone.utc)

# Foundational Prompt 1 seed epoch — preserved for ID/time compatibility.
FOUNDATIONAL_BASE = datetime(2026, 1, 6, 9, 0, 0, tzinfo=timezone.utc)

MANIFEST_SIGNAL_TYPE = "demo_dataset_manifest"
MANIFEST_SOURCE_RECORD_ID = "novabank-enterprise-demo-v2-manifest"

SYNTHETIC_DISCLAIMER = (
    "NovaBank is a fictional composite organization created solely for "
    "controlled product demonstration and testing. It is not affiliated with "
    "any real bank or company. All engineers, evidence and outcomes are "
    "synthetic and production-ineligible. Uncalibrated scores are not "
    "probabilities. Scenario results are decision-support only and are not "
    "causal claims."
)

PRODUCTION_INELIGIBLE = True
