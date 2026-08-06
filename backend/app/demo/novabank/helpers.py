"""Shared seed helpers for NovaBank Prompt 9 generators."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.demo.novabank.constants import AS_OF_AT, FOUNDATIONAL_BASE, TENANT_ID
from app.domain.enterprise_identifiers import build_entity_id


def tid(prefix: str, *parts: str) -> str:
    return build_entity_id(prefix, TENANT_ID, *parts)


def ensure(session: Session, model: type, pk_value: str, columns: dict[str, Any]) -> int:
    """Create row if absent. Returns 1 when created, 0 when reused."""
    if session.get(model, pk_value) is not None:
        return 0
    session.add(model(tenant_id=TENANT_ID, **columns))
    session.flush()
    return 1


def dt_from_base(days: int = 0, hours: int = 0) -> datetime:
    value = FOUNDATIONAL_BASE + timedelta(days=days, hours=hours)
    if value > AS_OF_AT:
        return AS_OF_AT
    return value


def clamp_observed(value: datetime) -> datetime:
    if value > AS_OF_AT:
        return AS_OF_AT
    return value


def empty_summary(keys: list[str]) -> dict[str, int]:
    return {key: 0 for key in keys}


def resolve_foundational_ids() -> dict[str, str]:
    """Resolve deterministic IDs for foundational + Prompt 9 natural keys."""
    from app.demo.novabank import identities as idn

    ids: dict[str, str] = {"org": tid("org", "novabank")}
    for _name, code in idn.BUSINESS_UNITS:
        ids[f"bu:{code}"] = tid("bu", code)
    for _name, code, _bu in idn.DEPARTMENTS:
        ids[f"dept:{code}"] = tid("dept", code)
    for _name, slug, _dept, _tt, _mission in idn.TEAMS:
        ids[f"team:{slug}"] = tid("team", slug)
    for _name, key, _team, _level in idn.ENGINEERS:
        ids[f"eng:{key}"] = tid("eng", key)
    for _name, slug, _cat in idn.CAPABILITIES:
        ids[f"cap:{slug}"] = tid("cap", slug)
    for _name, slug, _cat in idn.SKILLS:
        ids[f"skill:{slug}"] = tid("skill", slug)
    for _name, slug, _p, _c in idn.INITIATIVES:
        ids[f"init:{slug}"] = tid("init", slug)
    for _name, slug, _init, _team in idn.PROJECTS:
        ids[f"proj:{slug}"] = tid("proj", slug)
    for name, _team in idn.REPOSITORIES:
        ids[f"repo:{name}"] = tid("repo", "github", f"novabank/{name}")
    return ids
