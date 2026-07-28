"""Delivery Graph domain DTOs (Phase 3 Prompt 3).

Framework-light Pydantic models. No ORM leakage. Graph confidence is
deterministic evidence-support scoring — not Phase 2 assessment confidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.graph_enums import (
    GraphAnalysisRunState,
    GraphDataQualityWarning,
    GraphEdgeOrigin,
    GraphEdgeType,
    GraphFindingSeverity,
    GraphFindingStatus,
    GraphFindingType,
    GraphNodeType,
    GraphProjectionMode,
    GraphProjectionRunState,
)

MAX_DISPLAY_LABEL_LEN = 128
MAX_EDGE_ATTRIBUTES_BYTES = 2048
MAX_AFFECTED_NODE_IDS = 200
MAX_SUPPORTING_IDS = 100
FORBIDDEN_GRAPH_ATTRIBUTE_KEYS = frozenset(
    {
        "password",
        "token",
        "secret",
        "credential",
        "authorization",
        "email",
        "salary",
        "ssn",
        "raw_payload",
        "provider_payload",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _validate_interval(
    start: datetime,
    end: datetime | None,
    end_name: str,
    start_name: str,
    *,
    strict: bool = False,
) -> None:
    if end is None:
        return
    if strict:
        if end <= start:
            raise ValueError(f"{end_name} must be later than {start_name}")
    elif end <= start:
        raise ValueError(f"{end_name} must be later than {start_name}")


class TenantScopedGraph(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)

    tenant_id: str = Field(min_length=2, max_length=64)


class DeliveryGraphNode(TenantScopedGraph):
    graph_node_id: str = Field(min_length=1, max_length=64)
    node_type: GraphNodeType
    entity_id: str = Field(min_length=1, max_length=64)
    canonical_key: str = Field(min_length=1, max_length=256)
    display_label: str = Field(min_length=1, max_length=MAX_DISPLAY_LABEL_LEN)
    source_entity_version: str | None = Field(default=None, max_length=32)
    first_observed_at: datetime
    last_observed_at: datetime
    archived_at: datetime | None = None
    projection_version: str = Field(default="1", max_length=16)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def _check(self) -> DeliveryGraphNode:
        # Normalize SQLite naive UTC round-trips before comparison.
        if self.first_observed_at.tzinfo is None:
            self.first_observed_at = self.first_observed_at.replace(tzinfo=timezone.utc)
        if self.last_observed_at.tzinfo is None:
            self.last_observed_at = self.last_observed_at.replace(tzinfo=timezone.utc)
        if self.last_observed_at < self.first_observed_at:
            raise ValueError("last_observed_at must be >= first_observed_at")
        return self


class DeliveryGraphEdge(TenantScopedGraph):
    graph_edge_id: str = Field(min_length=1, max_length=64)
    source_node_id: str = Field(min_length=1, max_length=64)
    target_node_id: str = Field(min_length=1, max_length=64)
    edge_type: GraphEdgeType
    edge_origin: GraphEdgeOrigin
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    criticality: str = Field(default="medium", max_length=16)
    valid_from: datetime
    valid_to: datetime | None = None
    first_observed_at: datetime
    last_observed_at: datetime
    supporting_evidence_signal_id: str | None = Field(default=None, max_length=64)
    supporting_ownership_id: str | None = Field(default=None, max_length=64)
    supporting_dependency_id: str | None = Field(default=None, max_length=64)
    derivation_rule: str | None = Field(default=None, max_length=128)
    derivation_version: str | None = Field(default=None, max_length=16)
    attributes: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = Field(min_length=64, max_length=64)
    projection_version: str = Field(default="1", max_length=16)
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("attributes")
    @classmethod
    def _bounded_attributes(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("attributes must be a dict")
        lowered = {str(k).lower() for k in value}
        bad = lowered & FORBIDDEN_GRAPH_ATTRIBUTE_KEYS
        if bad:
            raise ValueError(f"Forbidden graph attribute keys: {sorted(bad)}")
        # Bound serialized size without importing json at module import cost
        import json

        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        if len(encoded.encode("utf-8")) > MAX_EDGE_ATTRIBUTES_BYTES:
            raise ValueError(f"attributes exceed {MAX_EDGE_ATTRIBUTES_BYTES} byte bound")
        return value

    @model_validator(mode="after")
    def _check(self) -> DeliveryGraphEdge:
        if self.source_node_id == self.target_node_id:
            raise ValueError("Self-edges are rejected")
        for attr in ("valid_from", "first_observed_at", "last_observed_at"):
            value = getattr(self, attr)
            if value is not None and value.tzinfo is None:
                setattr(self, attr, value.replace(tzinfo=timezone.utc))
        if self.valid_to is not None and self.valid_to.tzinfo is None:
            self.valid_to = self.valid_to.replace(tzinfo=timezone.utc)
        _validate_interval(self.valid_from, self.valid_to, "valid_to", "valid_from")
        if self.last_observed_at < self.first_observed_at:
            raise ValueError("last_observed_at must be >= first_observed_at")
        if self.edge_origin in {GraphEdgeOrigin.CONNECTOR, GraphEdgeOrigin.DERIVED}:
            has_provenance = any(
                [
                    self.supporting_evidence_signal_id,
                    self.supporting_ownership_id,
                    self.supporting_dependency_id,
                    self.derivation_rule,
                ]
            )
            if not has_provenance:
                raise ValueError(
                    "Connector and derived edges require provenance "
                    "(evidence/ownership/dependency id or derivation_rule)"
                )
        if self.edge_origin == GraphEdgeOrigin.DERIVED and not self.derivation_rule:
            raise ValueError("Derived edges require derivation_rule")
        return self


class GraphProjectionRun(TenantScopedGraph):
    graph_projection_run_id: str = Field(min_length=1, max_length=64)
    mode: GraphProjectionMode
    projection_version: str = Field(default="1", max_length=16)
    state: GraphProjectionRunState = GraphProjectionRunState.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    nodes_examined: int = Field(default=0, ge=0)
    nodes_created: int = Field(default=0, ge=0)
    nodes_updated: int = Field(default=0, ge=0)
    nodes_archived: int = Field(default=0, ge=0)
    edges_examined: int = Field(default=0, ge=0)
    edges_created: int = Field(default=0, ge=0)
    edges_updated: int = Field(default=0, ge=0)
    edges_closed: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
    sanitized_error_summary: str | None = Field(default=None, max_length=1024)
    source_high_watermark: datetime | None = None
    subject_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None


class GraphAnalysisRun(TenantScopedGraph):
    graph_analysis_run_id: str = Field(min_length=1, max_length=64)
    analysis_version: str = Field(default="1", max_length=16)
    graph_projection_version: str = Field(default="1", max_length=16)
    state: GraphAnalysisRunState = GraphAnalysisRunState.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    findings_created: int = Field(default=0, ge=0)
    findings_resolved: int = Field(default=0, ge=0)
    findings_observed: int = Field(default=0, ge=0)
    sanitized_error_summary: str | None = Field(default=None, max_length=1024)
    created_at: datetime | None = None


class GraphFinding(TenantScopedGraph):
    graph_finding_id: str = Field(min_length=1, max_length=64)
    finding_type: GraphFindingType
    status: GraphFindingStatus = GraphFindingStatus.ACTIVE
    severity: GraphFindingSeverity = GraphFindingSeverity.MEDIUM
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    title: str = Field(min_length=1, max_length=256)
    explanation: str = Field(min_length=1, max_length=2048)
    primary_node_id: str = Field(min_length=1, max_length=64)
    affected_node_ids: list[str] = Field(default_factory=list)
    supporting_edge_ids: list[str] = Field(default_factory=list)
    supporting_evidence_signal_ids: list[str] = Field(default_factory=list)
    data_quality_warnings: list[GraphDataQualityWarning] = Field(default_factory=list)
    rule_id: str = Field(min_length=1, max_length=128)
    rule_version: str = Field(default="1", max_length=16)
    detected_at: datetime
    last_observed_at: datetime
    resolved_at: datetime | None = None
    finding_hash: str = Field(min_length=64, max_length=64)
    created_at: datetime | None = None

    @field_validator("affected_node_ids")
    @classmethod
    def _bound_affected(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_AFFECTED_NODE_IDS:
            raise ValueError(f"affected_node_ids exceed {MAX_AFFECTED_NODE_IDS}")
        return value

    @field_validator("supporting_edge_ids", "supporting_evidence_signal_ids")
    @classmethod
    def _bound_supporting(cls, value: list[str]) -> list[str]:
        if len(value) > MAX_SUPPORTING_IDS:
            raise ValueError(f"supporting ids exceed {MAX_SUPPORTING_IDS}")
        return value

    @model_validator(mode="after")
    def _check(self) -> GraphFinding:
        if self.detected_at.tzinfo is None:
            self.detected_at = self.detected_at.replace(tzinfo=timezone.utc)
        if self.last_observed_at.tzinfo is None:
            self.last_observed_at = self.last_observed_at.replace(tzinfo=timezone.utc)
        if self.resolved_at is not None and self.resolved_at.tzinfo is None:
            self.resolved_at = self.resolved_at.replace(tzinfo=timezone.utc)
        if self.last_observed_at < self.detected_at:
            raise ValueError("last_observed_at must be >= detected_at")
        if self.status == GraphFindingStatus.RESOLVED and self.resolved_at is None:
            raise ValueError("resolved findings require resolved_at")
        return self


class GraphFindingEvidence(TenantScopedGraph):
    graph_finding_evidence_id: str = Field(min_length=1, max_length=64)
    graph_finding_id: str = Field(min_length=1, max_length=64)
    evidence_kind: str = Field(min_length=1, max_length=32)
    evidence_ref_id: str = Field(min_length=1, max_length=64)
    created_at: datetime | None = None


# ---------------------------------------------------------------------------
# Query response DTOs
# ---------------------------------------------------------------------------
class GraphNeighbor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge: DeliveryGraphEdge
    node: DeliveryGraphNode
    direction: str  # "incoming" | "outgoing"


class GraphPath(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_ids: list[str]
    edge_ids: list[str]
    length: int


class BlastRadiusResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origin_node_id: str
    directly_affected_node_ids: list[str]
    indirectly_affected_node_ids: list[str]
    affected_initiative_ids: list[str]
    affected_critical_initiative_ids: list[str]
    traversed_edge_ids: list[str]
    supporting_evidence_signal_ids: list[str]
    path_explanations: list[GraphPath]
    depth_used: int
    truncated: bool
    data_quality_warnings: list[GraphDataQualityWarning] = Field(default_factory=list)


class OwnershipConcentrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_node_id: str
    resource_node_type: GraphNodeType
    active_owner_count: int
    active_contributor_count: int
    primary_owner_node_ids: list[str]
    primary_owner_share: float | None = None
    concentration_score: float = Field(ge=0.0, le=1.0)
    single_owner: bool
    low_redundancy: bool
    supporting_edge_ids: list[str]
    supporting_evidence_signal_ids: list[str]
    data_quality_warnings: list[GraphDataQualityWarning] = Field(default_factory=list)


class DependencyCycleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_ids: list[str]
    edge_ids: list[str]
    canonical_key: str


class GraphSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    projection_version: str
    node_count: int
    edge_count: int
    active_edge_count: int
    nodes_by_type: dict[str, int]
    edges_by_type: dict[str, int]
    edges_by_origin: dict[str, int]
    active_finding_count: int
    findings_by_type: dict[str, int]
    latest_projection_run_id: str | None = None
    latest_analysis_run_id: str | None = None
    as_of: datetime
