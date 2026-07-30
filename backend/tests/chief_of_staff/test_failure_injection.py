"""Failure-injection transactional tests for Chief of Staff."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.services.chief_of_staff.service import ChiefOfStaffService

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def test_provider_path_failure_still_persists_fallback_brief(
    seeded_novabank, uow, novabank_tenant, monkeypatch
):
    """Azure path failure must persist fallback, not a partial success without brief."""
    from app.core.config import Settings
    from app.services.chief_of_staff.orchestration import ChiefOfStaffOrchestrator
    from app.services.chief_of_staff.provider_interface import CosProviderTimeoutError

    class Boom:
        def generate(self, *, evidence_package_json, prompt_bundle):
            raise CosProviderTimeoutError("injected timeout")

    settings = Settings(
        AI_ENABLED=True,
        AZURE_OPENAI_ENDPOINT="https://example.openai.azure.com",
        AZURE_OPENAI_API_KEY="test-key",
        AZURE_OPENAI_DEPLOYMENT="test-deploy",
    )
    orch = ChiefOfStaffOrchestrator(settings=settings, azure_provider=Boom())
    projects = uow.initiatives_projects.list_projects(novabank_tenant, limit=1, offset=0)
    service = ChiefOfStaffService(uow, orchestrator=orch)
    outcome = service.generate(
        novabank_tenant,
        ChiefOfStaffRequest(
            tenant_id=novabank_tenant.tenant_id,
            intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
            target_type=ChiefOfStaffTargetType.PROJECT,
            target_id=projects.items[0].enterprise_project_id,
            as_of_at=AS_OF,
            requested_provider=ChiefOfStaffProviderMode.AZURE_OPENAI,
        ),
    )
    assert outcome.brief is not None
    assert outcome.run.generation_state.value == "fallback_generated"
    assert outcome.run.failure_category.value == "timeout"
    claims = uow.cos_briefs.list_claims(novabank_tenant, outcome.brief.brief_id)
    assert claims


def test_brief_persistence_failure_rolls_back(seeded_novabank, uow, novabank_tenant, monkeypatch):
    projects = uow.initiatives_projects.list_projects(novabank_tenant, limit=1, offset=0)
    target_id = projects.items[0].enterprise_project_id
    service = ChiefOfStaffService(uow)
    original = uow.cos_briefs.persist_brief_bundle

    def boom(*args, **kwargs):
        raise RuntimeError("injected brief persistence failure")

    monkeypatch.setattr(uow.cos_briefs, "persist_brief_bundle", boom)
    before_runs = uow.cos_runs.list(novabank_tenant, limit=100, offset=0).total
    with pytest.raises(RuntimeError):
        service.generate(
            novabank_tenant,
            ChiefOfStaffRequest(
                tenant_id=novabank_tenant.tenant_id,
                intent=ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF,
                target_type=ChiefOfStaffTargetType.PROJECT,
                target_id=target_id,
                as_of_at=AS_OF,
                requested_provider=ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK,
            ),
        )
    # UoW rollback should prevent committed successful brief.
    after_runs = uow.cos_runs.list(novabank_tenant, limit=100, offset=0).total
    assert after_runs == before_runs
    monkeypatch.setattr(uow.cos_briefs, "persist_brief_bundle", original)
