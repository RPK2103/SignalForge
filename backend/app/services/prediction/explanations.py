"""Deterministic prediction factor explanations (no LLM, no person blame)."""

from __future__ import annotations

from typing import Any

from app.domain.enterprise_identifiers import build_entity_id
from app.domain.prediction_constants import MAX_FACTORS, SCORECARD_VERSION
from app.domain.prediction_enums import FactorSourceKind
from app.domain.prediction_models import (
    PredictionFactor,
    PredictionFeatureSnapshot,
    ScorecardResult,
)
from app.domain.tenant_context import TenantContext
from app.services.prediction.feature_schema import get_feature_meta

_POSITIVE_DIRECTION = "positive"
_NEGATIVE_DIRECTION = "negative"


def _feature_label(name: str) -> str:
    meta = get_feature_meta(name)
    if meta is None:
        return name.replace("_", " ")
    return str(meta.human_description)[:128]


def build_logistic_factors(
    ctx: TenantContext,
    *,
    delivery_prediction_id: str,
    snapshot: PredictionFeatureSnapshot,
    feature_list: list[str],
    coefficients: list[float],
    normalized_values: list[float],
    raw_values: list[float | None],
    imputed_flags: list[bool],
) -> list[PredictionFactor]:
    """Build top factors from logistic contributions in model space."""
    if len(coefficients) != len(feature_list):
        raise ValueError("coefficients must align with feature_list")
    contributions: list[tuple[str, float, float | None, float | None, float, bool]] = []
    for idx, name in enumerate(feature_list):
        if name.endswith("__missing"):
            continue
        coef = float(coefficients[idx])
        norm = float(normalized_values[idx]) if idx < len(normalized_values) else 0.0
        raw = raw_values[idx] if idx < len(raw_values) else None
        imputed = imputed_flags[idx] if idx < len(imputed_flags) else False
        contrib = coef * norm
        contributions.append((name, contrib, raw, norm, coef, imputed))

    contributions.sort(key=lambda item: abs(item[1]), reverse=True)
    selected = contributions[:MAX_FACTORS]

    lineage_by_name = {entry.feature_name: entry for entry in snapshot.feature_lineage}

    factors: list[PredictionFactor] = []
    for rank, (name, contrib, raw, norm, coef, imputed) in enumerate(selected, start=1):
        direction = _POSITIVE_DIRECTION if contrib >= 0.0 else _NEGATIVE_DIRECTION
        lineage = lineage_by_name.get(name)
        lineage_summary = None
        evidence_refs: list[str] = []
        if lineage is not None:
            lineage_summary = (
                f"{lineage.source_entity_type}:{lineage.source_entity_id}"
                f" via {lineage.transformation_rule}"
            )[:256]
            evidence_refs = [lineage.source_entity_id][:16]

        factors.append(
            PredictionFactor(
                tenant_id=ctx.tenant_id,
                prediction_factor_id=build_entity_id(
                    "pfac", ctx.tenant_id, delivery_prediction_id, str(rank), name
                ),
                delivery_prediction_id=delivery_prediction_id,
                rank=rank,
                source_kind=FactorSourceKind.LOGISTIC_CONTRIBUTION,
                feature_or_rule_id=name[:64],
                feature_label=_feature_label(name)[:128],
                direction=direction,
                contribution=float(contrib),
                feature_value=None if raw is None else float(raw),
                normalized_value=float(norm) if norm is not None else None,
                coefficient=float(coef),
                rule_version=None,
                was_imputed=bool(imputed),
                evidence_refs=evidence_refs,
                lineage_summary=lineage_summary,
            )
        )
    return factors


def build_scorecard_factors(
    ctx: TenantContext,
    *,
    delivery_prediction_id: str,
    scorecard: ScorecardResult,
) -> list[PredictionFactor]:
    """Build factors from deterministic scorecard rule contributions."""
    combined: list[tuple[str, float, dict[str, Any]]] = []
    for item in scorecard.positive_factors:
        rule_id = str(item.get("rule_id") or item.get("id") or "scorecard_rule")
        points = float(item.get("points") or item.get("contribution") or 0.0)
        combined.append((rule_id, points, item))
    for item in scorecard.negative_factors:
        rule_id = str(item.get("rule_id") or item.get("id") or "scorecard_rule")
        points = float(item.get("points") or item.get("contribution") or 0.0)
        combined.append((rule_id, points, item))

    combined.sort(key=lambda row: abs(row[1]), reverse=True)
    factors: list[PredictionFactor] = []
    for rank, (rule_id, points, item) in enumerate(combined[:MAX_FACTORS], start=1):
        direction = _POSITIVE_DIRECTION if points >= 0.0 else _NEGATIVE_DIRECTION
        label = str(item.get("label") or item.get("feature_label") or rule_id.replace("_", " "))
        refs = item.get("evidence_refs") or []
        if not isinstance(refs, list):
            refs = []
        factors.append(
            PredictionFactor(
                tenant_id=ctx.tenant_id,
                prediction_factor_id=build_entity_id(
                    "pfac", ctx.tenant_id, delivery_prediction_id, str(rank), rule_id
                ),
                delivery_prediction_id=delivery_prediction_id,
                rank=rank,
                source_kind=FactorSourceKind.SCORECARD_RULE,
                feature_or_rule_id=rule_id[:64],
                feature_label=label[:128],
                direction=direction,
                contribution=float(points),
                feature_value=None,
                normalized_value=None,
                coefficient=None,
                rule_version=str(item.get("rule_version") or SCORECARD_VERSION)[:32],
                was_imputed=False,
                evidence_refs=[str(r) for r in refs][:16],
                lineage_summary=str(item.get("lineage_summary") or "")[:256] or None,
            )
        )
    return factors


def build_explanation_summary(factors: list[PredictionFactor], *, reduced: bool) -> str:
    """Assemble a bounded template sentence. No person blame, no failure prophecy."""
    if not factors:
        if reduced:
            return "The estimate could not be refined due to limited delivery evidence."
        return "The estimate reflects balanced delivery signals across available features."

    # Prefer negative contributors when explaining risk elevation.
    focus = [f for f in factors if f.direction == _NEGATIVE_DIRECTION][:3]
    if not focus:
        focus = factors[:3]
    labels = [f.feature_label for f in focus]
    if len(labels) == 1:
        joined = labels[0]
    elif len(labels) == 2:
        joined = f"{labels[0]} and {labels[1]}"
    else:
        joined = f"{labels[0]}, {labels[1]} and {labels[2]}"

    if reduced:
        sentence = f"The estimate was reduced primarily by {joined}."
    else:
        sentence = f"The estimate was shaped primarily by {joined}."
    return sentence[:512]
