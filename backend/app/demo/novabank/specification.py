"""Immutable typed dataset contract for NovaBank Prompt 9."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from app.demo.novabank.constants import (
    AS_OF_AT,
    DATASET_NAME,
    DATASET_VERSION,
    GENERATOR_VERSION,
    SCHEMA_COMPAT,
    SYNTHETIC_DISCLAIMER,
)


@dataclass(frozen=True, slots=True)
class StoryDefinition:
    story_id: str
    title: str
    executive_question: str
    target_initiative_slug: str
    target_project_slug: str
    involved_team_slugs: tuple[str, ...]
    involved_repo_names: tuple[str, ...]
    evidence_categories: tuple[str, ...]
    scenario_name: str
    expected_qualitative_finding: str
    non_claims: tuple[str, ...]
    validation_assertions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DatasetSpecification:
    dataset_name: str
    dataset_version: str
    generator_version: str
    schema_compat: str
    as_of_at: datetime
    target_inventory: Mapping[str, int]
    stories: tuple[StoryDefinition, ...]
    disclaimer: str = SYNTHETIC_DISCLAIMER
    production_ineligible: bool = True

    def validate(self) -> None:
        if self.as_of_at.tzinfo is None:
            raise ValueError("as_of_at must be timezone-aware UTC")
        if self.as_of_at != AS_OF_AT:
            raise ValueError("as_of_at must equal the canonical AS_OF_AT constant")
        required = {
            "organizations",
            "business_units",
            "departments",
            "teams",
            "engineers",
            "capabilities",
            "skills",
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
        }
        missing = required - set(self.target_inventory)
        if missing:
            raise ValueError(f"target_inventory missing keys: {sorted(missing)}")
        # Roadmap ranges (Prompt 9).
        ranges = {
            "business_units": (5, 5),
            "teams": (10, 10),
            "engineers": (48, 48),
            "initiatives": (14, 14),
            "projects": (24, 24),
            "repositories": (32, 32),
            "capabilities": (18, 18),
            "sprints": (30, 30),
            "work_items": (450, 520),
            "pull_requests": (200, 250),
            "deployments": (70, 85),
            "incidents": (28, 40),
            "dependencies": (50, 70),
            "ownership": (100, 140),
            "availability": (15, 25),
        }
        for key, (lo, hi) in ranges.items():
            value = int(self.target_inventory[key])
            if value < lo or value > hi:
                raise ValueError(f"{key}={value} outside allowed range [{lo}, {hi}]")
        story_ids = [s.story_id for s in self.stories]
        if len(story_ids) != 8:
            raise ValueError("exactly eight stories required")
        if len(set(story_ids)) != 8:
            raise ValueError("story IDs must be unique")
        if sorted(story_ids) != story_ids:
            raise ValueError("stories must be ordered by story_id")


_STORIES: tuple[StoryDefinition, ...] = (
    StoryDefinition(
        story_id="story-01",
        title="Fraud-detection launch risk",
        executive_question="Can NovaBank safely deliver the next fraud-detection release?",
        target_initiative_slug="fraud-detection-uplift",
        target_project_slug="fraud-scoring-v2",
        involved_team_slugs=("fraud-detection", "customer-identity", "compliance-data"),
        involved_repo_names=("fraud-scoring", "identity-gateway", "compliance-reporting"),
        evidence_categories=(
            "dependency",
            "capability",
            "incident",
            "blocked_work",
            "ownership",
        ),
        scenario_name="STORY-01 FRAUD DETECTION LAUNCH RISK",
        expected_qualitative_finding=(
            "Delivery risk is evidence-backed via identity/compliance dependencies, "
            "capability constraint and elevated incident load."
        ),
        non_claims=(
            "No calibrated success probability",
            "No claim of production fraud-model accuracy",
            "No employee performance judgment",
        ),
        validation_assertions=(
            "fraud-scoring-v2 project exists",
            "dependency edges to identity or compliance exist",
            "incident evidence exists for fraud or identity repos",
            "scenario definition exists",
            "brief cites package evidence only",
        ),
    ),
    StoryDefinition(
        story_id="story-02",
        title="Payment-modernization dependency slip",
        executive_question="What happens when a shared payment-platform dependency slips?",
        target_initiative_slug="payment-modernization",
        target_project_slug="rt-payments-rail",
        involved_team_slugs=("payments-rails", "payment-api-platform", "payments-core"),
        involved_repo_names=("payments-rails-svc", "payment-api-gateway", "ledger-svc"),
        evidence_categories=("dependency", "blocked_work", "milestone", "availability"),
        scenario_name="STORY-02 PAYMENT DEPENDENCY SLIP",
        expected_qualitative_finding=(
            "Downstream initiatives are identifiable when the shared payment "
            "platform dependency revises its availability."
        ),
        non_claims=(
            "Dependency risk is not blamed on an individual",
            "No causal claim beyond evidence correlation",
        ),
        validation_assertions=(
            "cross-team payment dependency exists",
            "blocked work items exist on downstream projects",
            "scenario comparison path available",
        ),
    ),
    StoryDefinition(
        story_id="story-03",
        title="Azure-migration capability shortage",
        executive_question="Can the portfolio absorb an accelerated Azure migration?",
        target_initiative_slug="azure-migration",
        target_project_slug="core-banking-azure",
        involved_team_slugs=("cloud-foundations", "payments-core", "site-reliability"),
        involved_repo_names=("cloud-landing-zone", "payments-core-svc", "azure-policy-packs"),
        evidence_categories=("capability", "allocation", "competing_initiative"),
        scenario_name="STORY-03 AZURE CAPABILITY SHORTAGE",
        expected_qualitative_finding=(
            "Azure platform capability coverage is constrained while Cloud "
            "Foundation is overallocated across competing initiatives."
        ),
        non_claims=(
            "No Microsoft endorsement implied",
            "Scenario remains decision support only",
            "Evidence completeness must be stated",
        ),
        validation_assertions=(
            "azure-platform capability exists",
            "cloud-foundations allocation reduction exists",
            "capability gap discoverable in graph or ownership",
        ),
    ),
    StoryDefinition(
        story_id="story-04",
        title="Customer-copilot readiness",
        executive_question="Is the Customer Copilot initiative ready for executive commitment?",
        target_initiative_slug="customer-copilot-launch",
        target_project_slug="copilot-orchestration",
        involved_team_slugs=("customer-copilot", "compliance-data", "customer-identity"),
        involved_repo_names=(
            "customer-copilot-svc",
            "copilot-eval-harness",
            "identity-gateway",
        ),
        evidence_categories=(
            "dependency",
            "evidence_freshness",
            "ai_quality",
            "governance",
        ),
        scenario_name="STORY-04 CUSTOMER COPILOT READINESS",
        expected_qualitative_finding=(
            "Grounded brief with citations and known limitations; uncalibrated "
            "estimate semantics retained."
        ),
        non_claims=(
            "Uncalibrated score is not probability",
            "No claim of production AI readiness without evidence",
            "Candidate model not promoted",
        ),
        validation_assertions=(
            "customer-copilot-launch initiative exists",
            "freshness differences present across evidence subjects",
            "deterministic-fallback brief succeeds",
        ),
    ),
    StoryDefinition(
        story_id="story-05",
        title="Critical engineer role transition",
        executive_question="What changes if a key repository owner becomes unavailable?",
        target_initiative_slug="fraud-detection-uplift",
        target_project_slug="fraud-scoring-v2",
        involved_team_slugs=("fraud-detection",),
        involved_repo_names=("fraud-scoring", "data-lake-pipelines"),
        evidence_categories=("ownership_concentration", "availability", "review_redundancy"),
        scenario_name="STORY-05 KEY OWNER ROLE TRANSITION",
        expected_qualitative_finding=(
            "Knowledge-concentration and delivery-continuity risk for concentrated "
            "repositories under a hypothetical role transition."
        ),
        non_claims=(
            "Not a prediction about a person",
            "Not an employee-performance judgment",
            "No employee ranking",
        ),
        validation_assertions=(
            "concentrated ownership on fraud-scoring exists",
            "availability or role-transition event exists",
            "scenario is a safe counterfactual",
        ),
    ),
    StoryDefinition(
        story_id="story-06",
        title="Incident-driven roadmap delay",
        executive_question="How does elevated production-incident load affect roadmap delivery?",
        target_initiative_slug="reliability-program",
        target_project_slug="slo-platform",
        involved_team_slugs=("site-reliability", "cloud-foundations", "payments-core"),
        involved_repo_names=("payments-core-svc", "slo-controller", "observability-stack"),
        evidence_categories=("incident", "availability", "deployment", "delayed_work"),
        scenario_name="STORY-06 INCIDENT ROADMAP DELAY",
        expected_qualitative_finding=(
            "Temporal connection between incident spike, responder allocation and "
            "delayed roadmap work is visible without claiming proven causation."
        ),
        non_claims=(
            "Correlation is not proven causation",
            "No team-performance judgment",
        ),
        validation_assertions=(
            "incident spike exists near as_of window",
            "responder allocation evidence exists",
            "delayed sprint work exists",
        ),
    ),
    StoryDefinition(
        story_id="story-07",
        title="Concentrated repository ownership",
        executive_question="Which critical repositories lack resilient ownership?",
        target_initiative_slug="fraud-detection-uplift",
        target_project_slug="fraud-scoring-v2",
        involved_team_slugs=("fraud-detection", "payments-rails"),
        involved_repo_names=("fraud-scoring", "payments-rails-svc", "ledger-svc"),
        evidence_categories=("ownership_concentration", "capability", "comparison_repo"),
        scenario_name="STORY-07 CONCENTRATED OWNERSHIP RISK",
        expected_qualitative_finding=(
            "Bounded ownership concentration on critical repositories contrasts with "
            "healthy distributed ownership elsewhere."
        ),
        non_claims=("No productivity ranking", "No employee blame"),
        validation_assertions=(
            "concentrated ownership subset is bounded",
            "healthy comparison repositories exist",
            "critical capability linkage exists",
        ),
    ),
    StoryDefinition(
        story_id="story-08",
        title="Cross-team platform bottleneck",
        executive_question="Which initiatives compete for the same platform capacity?",
        target_initiative_slug="payment-modernization",
        target_project_slug="rt-payments-rail",
        involved_team_slugs=("cloud-foundations", "payments-rails", "payments-core"),
        involved_repo_names=("cloud-landing-zone", "payments-core-svc", "developer-portal"),
        evidence_categories=("shared_platform", "allocation", "review_queue", "dependency"),
        scenario_name="STORY-08 PLATFORM CAPACITY BOTTLENECK",
        expected_qualitative_finding=(
            "Shared Cloud Foundation capacity is a portfolio bottleneck across "
            "competing initiatives."
        ),
        non_claims=(
            "Capacity-system finding, not team-performance judgment",
            "Scenario output is not causal",
        ),
        validation_assertions=(
            "multiple initiatives depend on cloud-foundations or shared repos",
            "cloud-foundations overcommitment evidence exists",
            "capacity-decrease scenario exists",
        ),
    ),
)


TARGET_INVENTORY: dict[str, int] = {
    "organizations": 1,
    "business_units": 5,
    "departments": 10,
    "teams": 10,
    "engineers": 48,
    "capabilities": 18,
    "skills": 16,
    "capability_skills": 24,
    "initiatives": 14,
    "projects": 24,
    "repositories": 32,
    "sprints": 30,
    "work_items": 480,
    "pull_requests": 220,
    "deployments": 75,
    "incidents": 32,
    "dependencies": 58,
    "ownership": 120,
    "availability": 18,
    "data_sources": 3,
    "scenario_definitions": 8,
}


CANONICAL_SPEC = DatasetSpecification(
    dataset_name=DATASET_NAME,
    dataset_version=DATASET_VERSION,
    generator_version=GENERATOR_VERSION,
    schema_compat=SCHEMA_COMPAT,
    as_of_at=AS_OF_AT,
    target_inventory=TARGET_INVENTORY,
    stories=_STORIES,
)

CANONICAL_SPEC.validate()
