"""CLI tests for Chief of Staff."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from app.chief_of_staff.cli import main
from app.domain.chief_of_staff_enums import (
    ChiefOfStaffIntent,
    ChiefOfStaffProviderMode,
    ChiefOfStaffTargetType,
)
from app.domain.chief_of_staff_models import ChiefOfStaffRequest
from app.services.chief_of_staff.service import ChiefOfStaffService

AS_OF = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def test_cli_generate_and_quality(seeded_novabank, uow, novabank_tenant, monkeypatch, capsys):
    projects = uow.initiatives_projects.list_projects(novabank_tenant, limit=1, offset=0)
    target_id = projects.items[0].enterprise_project_id

    # Point CLI session at the same migrated DB by monkeypatching session factory.
    from sqlalchemy.orm import Session

    from app.db.session import get_engine
    import app.chief_of_staff.cli as cli

    def _session():
        return Session(get_engine())

    monkeypatch.setattr(cli, "_session", _session)

    code = main(
        [
            "generate",
            "--tenant-id",
            novabank_tenant.tenant_id,
            "--intent",
            ChiefOfStaffIntent.DELIVERY_STATUS_BRIEF.value,
            "--target-type",
            ChiefOfStaffTargetType.PROJECT.value,
            "--target-id",
            target_id,
            "--as-of",
            AS_OF.isoformat(),
            "--provider",
            ChiefOfStaffProviderMode.DETERMINISTIC_FALLBACK.value,
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "run_id" in payload
    assert "brief_id" in payload
    assert "evidence_hash" in payload
    assert "output_hash" in payload
    assert "api_key" not in out.lower()
    assert "Bearer" not in out

    code_q = main(["quality", "--tenant-id", novabank_tenant.tenant_id])
    assert code_q == 0


def test_cli_validate_review_compare(seeded_novabank, uow, novabank_tenant, monkeypatch, capsys):
    import app.chief_of_staff.cli as cli
    from sqlalchemy.orm import Session

    from app.db.session import get_engine

    monkeypatch.setattr(cli, "_session", lambda: Session(get_engine()))
    projects = uow.initiatives_projects.list_projects(novabank_tenant, limit=1, offset=0)
    target_id = projects.items[0].enterprise_project_id
    service = ChiefOfStaffService(uow)
    prior = service.generate(
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
    current = service.generate(
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
    assert main(["validate", "--tenant-id", novabank_tenant.tenant_id, "--brief-id", current.brief.brief_id]) == 0
    assert (
        main(
            [
                "compare",
                "--tenant-id",
                novabank_tenant.tenant_id,
                "--current-brief-id",
                current.brief.brief_id,
                "--prior-brief-id",
                prior.brief.brief_id,
            ]
        )
        == 0
    )
    assert (
        main(
            [
                "review",
                "--tenant-id",
                novabank_tenant.tenant_id,
                "--brief-id",
                current.brief.brief_id,
                "--state",
                "accepted",
                "--notes",
                "looks good",
            ]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "azure_openai_api_key" not in out.lower()
