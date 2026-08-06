"""NovaBank demo tenant orchestration service (Phase 3 Prompt 9)."""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.orm import Session

from app.db.prediction_seed import seed_prediction_history
from app.db.unit_of_work import UnitOfWork
from app.demo.novabank.constants import (
    AS_OF_AT,
    DATASET_VERSION,
    GENERATOR_VERSION,
    TENANT_ID,
)
from app.demo.novabank.evidence import seed_evidence_and_relationships
from app.demo.novabank.execution_history import seed_execution_history
from app.demo.novabank.helpers import empty_summary
from app.demo.novabank.intelligence import materialize_intelligence
from app.demo.novabank.manifest import build_manifest, load_manifest, persist_manifest
from app.demo.novabank.organization import seed_organization, seed_people_and_catalog
from app.demo.novabank.portfolio import seed_portfolio
from app.demo.novabank.scenarios import seed_story_scenarios
from app.demo.novabank.specification import CANONICAL_SPEC
from app.demo.novabank.validation import ValidationReport, validate_dataset
from app.security.audit import AuditWriteError, SecurityAuditService
from app.security.authorization import AuthorizationService
from app.security.context import SecurityContext
from app.security.enums import Permission, SecurityAuditAction
from app.security.exceptions import AuthorizationError
from app.security.rls import set_transaction_tenant

_logger = logging.getLogger("app.demo.novabank.service")

_SUMMARY_KEYS = [
    "organizations",
    "business_units",
    "departments",
    "teams",
    "engineers",
    "capabilities",
    "skills",
    "capability_skills",
    "capability_evidence",
    "skill_evidence",
    "capability_requirements",
    "initiatives",
    "projects",
    "repositories",
    "sprints",
    "work_items",
    "pull_requests",
    "deployments",
    "incidents",
    "dependencies",
    "ownership",
    "availability",
    "data_sources",
    "ingestion_runs",
    "evidence_signals",
    "delivery_outcomes",
    "manifest_signals",
]


class NovaBankDemoService:
    """Privileged, audited, transactional NovaBank demo dataset service."""

    def __init__(self, session: Session, security: SecurityContext | None) -> None:
        if security is None:
            raise AuthorizationError("security context required", reason_code="no_security_context")
        self._session = session
        self._security = security
        self._authz = AuthorizationService()
        self._uow = UnitOfWork(session)
        self._audit = SecurityAuditService(self._uow)

    def _require(self) -> None:
        self._authz.require(self._security, Permission.DEMO_TENANT_MANAGE, TENANT_ID)
        if self._security.tenant_id != TENANT_ID:
            raise AuthorizationError(
                "NovaBank demo service requires novabank tenant context",
                reason_code="tenant_mismatch",
            )

    def _apply_tenant_rls(self) -> None:
        """Set transaction-local Postgres RLS GUC for NovaBank writes/reads.

        No-op on SQLite. Required under FORCE RLS when the connection uses the
        non-bypass application role (CI PostgreSQL tenant-isolation job).
        """
        set_transaction_tenant(self._session, TENANT_ID)

    def seed(self, *, commit: bool = True) -> dict[str, Any]:
        """Idempotently seed the canonical Prompt 9 NovaBank dataset."""
        self._require()
        self._apply_tenant_rls()
        CANONICAL_SPEC.validate()
        started = time.perf_counter()
        summary = empty_summary(_SUMMARY_KEYS)
        try:
            ids = seed_organization(self._session, summary)
            seed_people_and_catalog(self._session, ids, summary)
            seed_portfolio(self._session, ids, summary)
            seed_execution_history(self._session, ids, summary)
            seed_evidence_and_relationships(self._session, ids, summary)
            # Synthetic prediction outcomes (production-ineligible).
            from sqlalchemy import inspect

            bind = self._session.get_bind()
            if bind is not None and "ent_delivery_outcomes" in inspect(bind).get_table_names():
                outcome_counts = seed_prediction_history(self._session)
                summary["delivery_outcomes"] += int(outcome_counts.get("delivery_outcomes", 0))

            scenario_summary = seed_story_scenarios(self._session)
            # Security principals (additive / idempotent).
            try:
                from app.security.novabank_seed import seed_novabank_security

                existing_principal = self._uow.security_principals.find_by_subject(
                    TENANT_ID, "novabank-admin-sub"
                )
                if existing_principal is None:
                    seed_novabank_security(self._uow, tenant_id=TENANT_ID)
            except Exception as exc:  # noqa: BLE001
                _logger.warning("demo.seed.security_skipped category=%s", type(exc).__name__)

            created = {k: v for k, v in summary.items() if v > 0}
            reused = {k: 0 for k in summary if summary[k] == 0}
            # Approximate reused: categories already present contribute 0 created.
            for key in summary:
                if summary[key] == 0:
                    reused[key] = 1

            manifest = build_manifest(self._session, created=created, reused=reused)
            ds_id = ids.get("ds:github")
            if ds_id is None:
                from app.demo.novabank.helpers import tid

                ds_id = tid("ds", "github", "NovaBank GitHub Org")
            summary["manifest_signals"] += persist_manifest(self._session, manifest, ds_id)

            audit_record = self._audit.record_sensitive_action(
                self._security,
                action=SecurityAuditAction.DEMO_DATASET_SEEDED,
                permission=Permission.DEMO_TENANT_MANAGE,
                resource_type="demo_dataset",
                resource_id=DATASET_VERSION,
                metadata={
                    "dataset_version": DATASET_VERSION,
                    "generator_version": GENERATOR_VERSION,
                    "created_categories": len(created),
                },
            )
            if audit_record is None:
                raise AuditWriteError("Fail-closed demo seed audit write failed")

            if commit:
                self._uow.commit()
            duration_ms = int((time.perf_counter() - started) * 1000)
            _logger.info(
                "demo.seed.complete dataset_version=%s duration_ms=%s created_total=%s",
                DATASET_VERSION,
                duration_ms,
                sum(summary.values()),
            )
            return {
                "dataset_version": DATASET_VERSION,
                "generator_version": GENERATOR_VERSION,
                "as_of_at": AS_OF_AT.isoformat().replace("+00:00", "Z"),
                "manifest_hash": manifest["manifest_hash"],
                "created": summary,
                "created_total": sum(summary.values()),
                "scenario": scenario_summary,
                "duration_ms": duration_ms,
                "synthetic": True,
                "production_ineligible": True,
            }
        except Exception:
            self._uow.rollback()
            _logger.warning(
                "demo.seed.failed dataset_version=%s category=seed_failure",
                DATASET_VERSION,
            )
            raise

    def materialize(self, *, commit: bool = True) -> dict[str, Any]:
        self._require()
        self._apply_tenant_rls()
        started = time.perf_counter()
        try:
            result = materialize_intelligence(self._session)
            if not result.get("ok") or result.get("errors"):
                # Honest failure: never commit a "successful" materialization when
                # any required stage reported errors.
                self._uow.rollback()
                raise RuntimeError(
                    "materialization incomplete: " + ",".join(result.get("errors") or ["unknown"])
                )
            if commit:
                self._uow.commit()
            result["duration_ms"] = int((time.perf_counter() - started) * 1000)
            result["dataset_version"] = DATASET_VERSION
            return result
        except Exception:
            self._uow.rollback()
            _logger.warning(
                "demo.materialize.failed dataset_version=%s category=materialize_failure",
                DATASET_VERSION,
            )
            raise

    def validate(self) -> ValidationReport:
        self._require()
        self._apply_tenant_rls()
        return validate_dataset(self._session)

    def manifest(self) -> dict[str, Any]:
        self._require()
        self._apply_tenant_rls()
        loaded = load_manifest(self._session)
        if loaded is not None:
            return loaded
        return build_manifest(self._session)

    def report(self) -> dict[str, Any]:
        self._require()
        self._apply_tenant_rls()
        validation = self.validate()
        return {
            "dataset_version": DATASET_VERSION,
            "generator_version": GENERATOR_VERSION,
            "as_of_at": AS_OF_AT.isoformat().replace("+00:00", "Z"),
            "validation": validation.to_dict(),
            "manifest": self.manifest(),
            "stories": [
                {
                    "story_id": s.story_id,
                    "title": s.title,
                    "executive_question": s.executive_question,
                    "scenario_name": s.scenario_name,
                }
                for s in CANONICAL_SPEC.stories
            ],
        }
