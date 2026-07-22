"""Accumulates and reconciles deterministic score contributions."""

from app.domain.models import DecisionTraceEntry
from app.domain.policy import get_policy


class DecisionTraceService:
    def __init__(self, policy_version: str | None = None):
        policy = get_policy(policy_version)
        self._policy_version = policy.POLICY_VERSION
        self._entries: list[DecisionTraceEntry] = []

    @property
    def policy_version(self) -> str:
        return self._policy_version

    @property
    def entries(self) -> list[DecisionTraceEntry]:
        return list(self._entries)

    def add(
        self,
        step: str,
        component: str,
        label: str,
        value: str,
        contribution: float,
    ) -> None:
        self._entries.append(
            DecisionTraceEntry(
                step=step,
                component=component,
                label=label,
                value=value,
                contribution=contribution,
                policy_version=self._policy_version,
            )
        )

    def total_contribution(self) -> float:
        return sum(entry.contribution for entry in self._entries)

    def reconcile_to_score(self, raw_total: float) -> tuple[int, float]:
        """Return clamped score and reconciliation delta."""
        clamped = max(0, min(100, round(raw_total)))
        delta = clamped - raw_total
        return clamped, delta
