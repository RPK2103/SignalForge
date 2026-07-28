"""Bounded, deterministic graph algorithms for the Delivery Graph.

Complexity notes (n=nodes, m=edges, d=max_depth, B=node/edge budgets):
- bounded_bfs: O(min(n, B_nodes) + min(m, B_edges)) with depth cap d
- shortest_path: BFS O(min(n, B_nodes) + min(m, B_edges))
- reachability: same as BFS
- detect_cycles: iterative DFS O(n + m) with visit budget
- blast_radius: BFS with typed accounting, same bounds

No recursion is used for traversal (avoids recursion-depth DoS).
No all-path enumeration (exponential risk).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from app.domain.graph_enums import GraphEdgeType
from app.domain.graph_models import DeliveryGraphEdge, DependencyCycleResult, GraphPath
from app.services.enterprise.exceptions import EnterpriseValidationError

DEFAULT_MAX_DEPTH = 6
DEFAULT_MAX_NODES = 500
DEFAULT_MAX_EDGES = 2000
DEFAULT_MAX_PATHS = 20
DEFAULT_OPERATION_BUDGET = 50_000


@dataclass(frozen=True)
class TraversalBounds:
    max_depth: int = DEFAULT_MAX_DEPTH
    max_nodes: int = DEFAULT_MAX_NODES
    max_edges: int = DEFAULT_MAX_EDGES
    max_paths: int = DEFAULT_MAX_PATHS
    operation_budget: int = DEFAULT_OPERATION_BUDGET

    def validated(self) -> TraversalBounds:
        if self.max_depth < 1 or self.max_depth > 20:
            raise EnterpriseValidationError("max_depth must be between 1 and 20")
        if self.max_nodes < 1 or self.max_nodes > 5000:
            raise EnterpriseValidationError("max_nodes must be between 1 and 5000")
        if self.max_edges < 1 or self.max_edges > 20_000:
            raise EnterpriseValidationError("max_edges must be between 1 and 20000")
        if self.max_paths < 1 or self.max_paths > 100:
            raise EnterpriseValidationError("max_paths must be between 1 and 100")
        if self.operation_budget < 100 or self.operation_budget > 1_000_000:
            raise EnterpriseValidationError("operation_budget must be between 100 and 1000000")
        return self


@dataclass
class TraversalStats:
    nodes_visited: int = 0
    edges_visited: int = 0
    operations: int = 0
    truncated: bool = False
    reject_reason: str | None = None


@dataclass
class Adjacency:
    """Deterministic adjacency built from a bounded edge list."""

    outgoing: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    # node_id -> list[(neighbor_id, edge_id)]
    incoming: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    edges_by_id: dict[str, DeliveryGraphEdge] = field(default_factory=dict)

    @classmethod
    def from_edges(cls, edges: list[DeliveryGraphEdge]) -> Adjacency:
        adj = cls()
        # Deterministic neighbor order by edge_id then neighbor id.
        sorted_edges = sorted(
            edges, key=lambda e: (e.graph_edge_id, e.source_node_id, e.target_node_id)
        )
        for edge in sorted_edges:
            adj.edges_by_id[edge.graph_edge_id] = edge
            adj.outgoing.setdefault(edge.source_node_id, []).append(
                (edge.target_node_id, edge.graph_edge_id)
            )
            adj.incoming.setdefault(edge.target_node_id, []).append(
                (edge.source_node_id, edge.graph_edge_id)
            )
        for node_id in adj.outgoing:
            adj.outgoing[node_id].sort(key=lambda t: (t[1], t[0]))
        for node_id in adj.incoming:
            adj.incoming[node_id].sort(key=lambda t: (t[1], t[0]))
        return adj


def _budget_check(stats: TraversalStats, bounds: TraversalBounds) -> bool:
    stats.operations += 1
    if stats.operations > bounds.operation_budget:
        stats.truncated = True
        stats.reject_reason = "operation_budget_exceeded"
        return False
    if stats.nodes_visited > bounds.max_nodes:
        stats.truncated = True
        stats.reject_reason = "node_budget_exceeded"
        return False
    if stats.edges_visited > bounds.max_edges:
        stats.truncated = True
        stats.reject_reason = "edge_budget_exceeded"
        return False
    return True


def bounded_bfs(
    adjacency: Adjacency,
    origin: str,
    *,
    bounds: TraversalBounds,
    direction: str = "outgoing",
) -> tuple[dict[str, int], dict[str, str | None], dict[str, str | None], TraversalStats]:
    """BFS returning (distance, parent_node, parent_edge, stats)."""
    bounds = bounds.validated()
    stats = TraversalStats()
    if origin not in adjacency.outgoing and origin not in adjacency.incoming:
        # Isolated origin is still valid.
        stats.nodes_visited = 1
        return {origin: 0}, {origin: None}, {origin: None}, stats

    distances: dict[str, int] = {origin: 0}
    parents: dict[str, str | None] = {origin: None}
    parent_edges: dict[str, str | None] = {origin: None}
    queue: deque[str] = deque([origin])
    stats.nodes_visited = 1

    while queue:
        if not _budget_check(stats, bounds):
            break
        current = queue.popleft()
        depth = distances[current]
        if depth >= bounds.max_depth:
            continue
        neighbors = (
            adjacency.outgoing.get(current, [])
            if direction == "outgoing"
            else adjacency.incoming.get(current, [])
        )
        if direction == "both":
            neighbors = sorted(
                set(adjacency.outgoing.get(current, [])) | set(adjacency.incoming.get(current, [])),
                key=lambda t: (t[1], t[0]),
            )
        for neighbor, edge_id in neighbors:
            stats.edges_visited += 1
            if not _budget_check(stats, bounds):
                return distances, parents, parent_edges, stats
            if neighbor in distances:
                continue
            distances[neighbor] = depth + 1
            parents[neighbor] = current
            parent_edges[neighbor] = edge_id
            stats.nodes_visited += 1
            queue.append(neighbor)
            if stats.nodes_visited > bounds.max_nodes:
                stats.truncated = True
                stats.reject_reason = "node_budget_exceeded"
                return distances, parents, parent_edges, stats
    return distances, parents, parent_edges, stats


def reconstruct_path(
    target: str,
    parents: dict[str, str | None],
    parent_edges: dict[str, str | None],
) -> GraphPath | None:
    if target not in parents:
        return None
    nodes: list[str] = []
    edges: list[str] = []
    current: str | None = target
    guard = 0
    while current is not None:
        nodes.append(current)
        edge_id = parent_edges.get(current)
        if edge_id is not None:
            edges.append(edge_id)
        current = parents.get(current)
        guard += 1
        if guard > 10_000:
            return None
    nodes.reverse()
    edges.reverse()
    return GraphPath(node_ids=nodes, edge_ids=edges, length=len(edges))


def shortest_path(
    adjacency: Adjacency,
    source: str,
    target: str,
    *,
    bounds: TraversalBounds,
) -> tuple[GraphPath | None, TraversalStats]:
    distances, parents, parent_edges, stats = bounded_bfs(
        adjacency, source, bounds=bounds, direction="outgoing"
    )
    if target not in distances:
        return None, stats
    return reconstruct_path(target, parents, parent_edges), stats


def reachability(
    adjacency: Adjacency,
    origin: str,
    *,
    bounds: TraversalBounds,
    direction: str = "outgoing",
) -> tuple[list[str], TraversalStats]:
    distances, _, _, stats = bounded_bfs(adjacency, origin, bounds=bounds, direction=direction)
    reachable = sorted(
        [node for node, depth in distances.items() if depth > 0],
        key=lambda n: (distances[n], n),
    )
    return reachable, stats


def detect_dependency_cycles(
    edges: list[DeliveryGraphEdge],
    *,
    bounds: TraversalBounds,
    edge_types: set[GraphEdgeType] | None = None,
) -> tuple[list[DependencyCycleResult], TraversalStats]:
    """Detect directed cycles among dependency-like edges.

    Canonical cycle representation: rotate so the lexicographically smallest
    node id is first; reverse orientation is not emitted.
    """
    bounds = bounds.validated()
    stats = TraversalStats()
    allowed = edge_types or {
        GraphEdgeType.DEPENDS_ON,
        GraphEdgeType.BLOCKS,
        GraphEdgeType.REQUIRES,
        GraphEdgeType.SUPPORTS,
    }
    filtered = [e for e in edges if e.edge_type in allowed]
    adj = Adjacency.from_edges(filtered)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = defaultdict(int)
    parent: dict[str, str | None] = {}
    parent_edge: dict[str, str | None] = {}
    cycles: list[DependencyCycleResult] = []
    seen_keys: set[str] = set()

    nodes = sorted(set(adj.outgoing) | set(adj.incoming))

    for start in nodes:
        if color[start] != WHITE:
            continue
        # Iterative DFS stack: (node, next_neighbor_index)
        stack: list[tuple[str, int]] = [(start, 0)]
        color[start] = GRAY
        parent[start] = None
        parent_edge[start] = None
        stats.nodes_visited += 1

        while stack:
            if not _budget_check(stats, bounds):
                return _sorted_cycles(cycles), stats
            node, idx = stack[-1]
            neighbors = adj.outgoing.get(node, [])
            if idx >= len(neighbors):
                color[node] = BLACK
                stack.pop()
                continue
            stack[-1] = (node, idx + 1)
            neighbor, edge_id = neighbors[idx]
            stats.edges_visited += 1
            if color[neighbor] == GRAY:
                # Found cycle.
                cycle_nodes = [neighbor]
                cycle_edges = [edge_id]
                cursor = node
                guard = 0
                while cursor != neighbor and cursor is not None:
                    cycle_nodes.append(cursor)
                    pe = parent_edge.get(cursor)
                    if pe:
                        cycle_edges.append(pe)
                    cursor = parent.get(cursor)
                    guard += 1
                    if guard > bounds.max_nodes:
                        break
                cycle_nodes.reverse()
                cycle_edges.reverse()
                canonical = _canonicalize_cycle(cycle_nodes, cycle_edges)
                if canonical.canonical_key not in seen_keys:
                    seen_keys.add(canonical.canonical_key)
                    cycles.append(canonical)
                continue
            if color[neighbor] == WHITE:
                color[neighbor] = GRAY
                parent[neighbor] = node
                parent_edge[neighbor] = edge_id
                stats.nodes_visited += 1
                stack.append((neighbor, 0))

    return _sorted_cycles(cycles), stats


def _canonicalize_cycle(node_ids: list[str], edge_ids: list[str]) -> DependencyCycleResult:
    if not node_ids:
        return DependencyCycleResult(node_ids=[], edge_ids=[], canonical_key="")
    # Rotate to lexicographically smallest node.
    min_idx = min(range(len(node_ids)), key=lambda i: node_ids[i])
    rotated_nodes = node_ids[min_idx:] + node_ids[:min_idx]
    rotated_edges = edge_ids[min_idx:] + edge_ids[:min_idx]
    key = "|".join(rotated_nodes)
    return DependencyCycleResult(
        node_ids=rotated_nodes,
        edge_ids=rotated_edges,
        canonical_key=key,
    )


def _sorted_cycles(cycles: list[DependencyCycleResult]) -> list[DependencyCycleResult]:
    return sorted(cycles, key=lambda c: c.canonical_key)


def blast_radius_traversal(
    adjacency: Adjacency,
    origin: str,
    *,
    bounds: TraversalBounds,
    initiative_node_ids: set[str],
    critical_initiative_node_ids: set[str],
) -> tuple[dict, TraversalStats]:
    """Compute blast radius accounting from an origin node.

    Uses outgoing reachability (impact flows outward along dependency/
    ownership/contribution edges already loaded into adjacency).
    """
    distances, parents, parent_edges, stats = bounded_bfs(
        adjacency, origin, bounds=bounds, direction="outgoing"
    )
    direct = sorted([n for n, d in distances.items() if d == 1])
    indirect = sorted([n for n, d in distances.items() if d > 1])
    affected_inits = sorted([n for n in distances if n in initiative_node_ids and n != origin])
    critical_inits = sorted(
        [n for n in distances if n in critical_initiative_node_ids and n != origin]
    )
    traversed_edges = sorted({eid for eid in parent_edges.values() if eid is not None})
    paths: list[GraphPath] = []
    # Explain paths to critical initiatives first, then initiatives, then sample.
    targets = critical_inits + [i for i in affected_inits if i not in critical_inits]
    for target in targets:
        if len(paths) >= bounds.max_paths:
            stats.truncated = True
            stats.reject_reason = stats.reject_reason or "path_budget_exceeded"
            break
        path = reconstruct_path(target, parents, parent_edges)
        if path is not None:
            paths.append(path)

    return {
        "directly_affected_node_ids": direct,
        "indirectly_affected_node_ids": indirect,
        "affected_initiative_ids": affected_inits,
        "affected_critical_initiative_ids": critical_inits,
        "traversed_edge_ids": traversed_edges,
        "path_explanations": paths,
        "depth_used": max(distances.values()) if distances else 0,
        "truncated": stats.truncated,
    }, stats


def ownership_concentration_score(
    *,
    primary_count: int,
    contributor_count: int,
    primary_allocations: list[int] | None = None,
) -> tuple[float, float | None, bool, bool]:
    """Deterministic concentration metrics.

    Returns (concentration_score, primary_owner_share, single_owner, low_redundancy).

    concentration_score in [0,1]: 1.0 means maximum concentration (single owner).
    Does NOT use commit counts or employee ranking.
    """
    owners = max(0, primary_count)
    contributors = max(0, contributor_count)
    if owners == 0 and contributors == 0:
        return 0.0, None, False, False
    if owners == 0:
        # Contributors only — treat as low concentration but flag low redundancy.
        return 0.4, None, False, True
    if owners <= 1 and contributors == 0:
        share = 1.0
        return 1.0, share, True, True
    if owners == 1:
        share = 1.0
        # Low redundancy if no secondary/contributor coverage.
        low = contributors == 0
        return 0.85 if not low else 1.0, share, True, low
    if primary_allocations:
        total_alloc = sum(primary_allocations) or 1
        max_share = max(primary_allocations) / total_alloc
        # Herfindahl-like normalized by owner count.
        hhi = sum((a / total_alloc) ** 2 for a in primary_allocations)
        return min(1.0, hhi), max_share, False, owners < 2
    # Equal-share assumption when allocations missing.
    share = 1.0 / owners
    concentration = 1.0 / owners
    return concentration, share, False, owners < 2
