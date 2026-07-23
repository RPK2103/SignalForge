export type CapabilityCategory =
  | "backend"
  | "cloud"
  | "ai"
  | "data"
  | "devops"
  | "architecture"
  | "security"
  | "delivery_execution";

export type CoverageLevel = "missing" | "weak" | "adequate" | "strong";

export type ConfidenceLevel = "low" | "medium" | "high";

export type RiskSeverity = "low" | "medium" | "high";

export type RiskFindingType =
  | "missing_critical_capability"
  | "weak_capability"
  | "key_person_dependency"
  | "incomplete_evidence"
  | "duplicate_team_member"
  | "empty_team";

export type ReadinessDimension =
  | "capability_coverage"
  | "skill_depth"
  | "team_balance"
  | "delivery_risk"
  | "evidence_quality";

export type EvidenceSource =
  | "skills"
  | "certifications"
  | "projects"
  | "experience";

export type SimulationOperationType = "add" | "remove" | "replace" | "compare";

export type SimulationChangeType =
  | "introduced"
  | "resolved"
  | "escalated"
  | "deescalated"
  | "improved"
  | "degraded"
  | "modified";

export type MitigationType =
  | "add_capability_coverage"
  | "strengthen_capability_coverage"
  | "establish_secondary_owner"
  | "preserve_critical_engineer"
  | "improve_engineer_evidence"
  | "reassess_project_scope"
  | "replace_with_stronger_match";

export type MitigationPriority = "critical" | "high" | "medium" | "low";

export type HumanReviewState = "accepted" | "overridden" | "needs_more_data";

export type LeadershipDecision =
  | "proceed"
  | "proceed_with_conditions"
  | "defer"
  | "do_not_proceed";

export type ProviderMode = "azure_openai" | "deterministic_fallback";

export type GenerationStatus =
  | "generated"
  | "fallback_generated"
  | "failed";

export type LeadershipBriefFailureCategory =
  | "ai_disabled"
  | "missing_configuration"
  | "timeout"
  | "authentication_error"
  | "rate_limited"
  | "provider_unavailable"
  | "malformed_output"
  | "schema_validation_failed"
  | "grounding_validation_failed"
  | "empty_output"
  | "unknown_provider_error";

export type LeadershipActionPriority = "critical" | "high" | "medium" | "low";

export type LeadershipBriefRiskSeverity = "low" | "medium" | "high";
