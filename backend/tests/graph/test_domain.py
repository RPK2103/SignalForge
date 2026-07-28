"""Domain model tests for Delivery Graph."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.domain.enterprise_identifiers import build_entity_id
from app.domain.graph_enums import (
    GraphEdgeOrigin,
    GraphEdgeType,
    GraphFindingType,
    GraphNodeType,
)
from app.domain.graph_models import (
    FORBIDDEN_GRAPH_ATTRIBUTE_KEYS,
    DeliveryGraphEdge,
    DeliveryGraphNode,
)
from app.services.persistence.snapshot_service import snapshot_hash

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)


def test_node_types_bounded():
    assert GraphNodeType.ENGINEER.value == "engineer"
    assert len(GraphNodeType) == 15


def test_edge_types_bounded():
    assert GraphEdgeType.DEPENDS_ON.value == "depends_on"
    assert len(GraphEdgeType) == 11


def test_finding_types_bounded():
    assert len(GraphFindingType) == 8


def test_deterministic_node_ids():
    a = build_entity_id("gnode", "novabank", "engineer", "eng-1")
    b = build_entity_id("gnode", "novabank", "engineer", "eng-1")
    c = build_entity_id("gnode", "tenant-b", "engineer", "eng-1")
    assert a == b
    assert a != c


def test_temporal_validation_rejects_invalid_interval():
    with pytest.raises(ValidationError):
        DeliveryGraphEdge(
            tenant_id="novabank",
            graph_edge_id="gedge_x",
            source_node_id="a",
            target_node_id="b",
            edge_type=GraphEdgeType.DEPENDS_ON,
            edge_origin=GraphEdgeOrigin.MANUAL,
            valid_from=NOW,
            valid_to=NOW - timedelta(days=1),
            first_observed_at=NOW,
            last_observed_at=NOW,
            supporting_dependency_id="dep_1",
            payload_hash=snapshot_hash({"x": 1}),
        )


def test_self_edge_rejected():
    with pytest.raises(ValidationError):
        DeliveryGraphEdge(
            tenant_id="novabank",
            graph_edge_id="gedge_x",
            source_node_id="same",
            target_node_id="same",
            edge_type=GraphEdgeType.DEPENDS_ON,
            edge_origin=GraphEdgeOrigin.MANUAL,
            valid_from=NOW,
            first_observed_at=NOW,
            last_observed_at=NOW,
            supporting_dependency_id="dep_1",
            payload_hash=snapshot_hash({"x": 1}),
        )


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        DeliveryGraphEdge(
            tenant_id="novabank",
            graph_edge_id="gedge_x",
            source_node_id="a",
            target_node_id="b",
            edge_type=GraphEdgeType.OWNS,
            edge_origin=GraphEdgeOrigin.MANUAL,
            confidence=1.5,
            valid_from=NOW,
            first_observed_at=NOW,
            last_observed_at=NOW,
            supporting_ownership_id="own_1",
            payload_hash=snapshot_hash({"x": 1}),
        )


def test_forbidden_attribute_keys():
    assert "email" in FORBIDDEN_GRAPH_ATTRIBUTE_KEYS
    with pytest.raises(ValidationError):
        DeliveryGraphEdge(
            tenant_id="novabank",
            graph_edge_id="gedge_x",
            source_node_id="a",
            target_node_id="b",
            edge_type=GraphEdgeType.OWNS,
            edge_origin=GraphEdgeOrigin.MANUAL,
            valid_from=NOW,
            first_observed_at=NOW,
            last_observed_at=NOW,
            supporting_ownership_id="own_1",
            attributes={"email": "secret@example.com"},
            payload_hash=snapshot_hash({"x": 1}),
        )


def test_derived_requires_derivation_rule():
    with pytest.raises(ValidationError):
        DeliveryGraphEdge(
            tenant_id="novabank",
            graph_edge_id="gedge_x",
            source_node_id="a",
            target_node_id="b",
            edge_type=GraphEdgeType.SUPPORTS,
            edge_origin=GraphEdgeOrigin.DERIVED,
            valid_from=NOW,
            first_observed_at=NOW,
            last_observed_at=NOW,
            payload_hash=snapshot_hash({"x": 1}),
        )


def test_node_display_label_bound():
    node = DeliveryGraphNode(
        tenant_id="novabank",
        graph_node_id="gnode_x",
        node_type=GraphNodeType.TEAM,
        entity_id="t1",
        canonical_key="team:t1",
        display_label="A" * 128,
        first_observed_at=NOW,
        last_observed_at=NOW,
    )
    assert len(node.display_label) == 128
    with pytest.raises(ValidationError):
        DeliveryGraphNode(
            tenant_id="novabank",
            graph_node_id="gnode_x",
            node_type=GraphNodeType.TEAM,
            entity_id="t1",
            canonical_key="team:t1",
            display_label="A" * 129,
            first_observed_at=NOW,
            last_observed_at=NOW,
        )
