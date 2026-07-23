import type {
  MitigationPriority,
  MitigationType,
  SimulationChangeType,
} from "./enums";
import type {
  EngineerProfile,
  ReadinessAssessResponse,
  SkillGap,
} from "./catalog";

export type AddSimulationOperation = {
  type: "add";
  engineer_id: string;
};

export type RemoveSimulationOperation = {
  type: "remove";
  engineer_id: string;
};

export type ReplaceSimulationOperation = {
  type: "replace";
  remove_engineer_id: string;
  add_engineer_id: string;
};

export type CompareSimulationOperation = {
  type: "compare";
  proposed_engineer_ids: string[];
};

export type SimulationOperation =
  | AddSimulationOperation
  | RemoveSimulationOperation
  | ReplaceSimulationOperation
  | CompareSimulationOperation;

export type SimulationRequest = {
  project_id: string;
  baseline_engineer_ids: string[];
  operation: SimulationOperation;
  policy_version?: string | null;
};

export type RiskFindingChange = {
  change_type: SimulationChangeType;
  finding_type: string;
  severity: string;
  baseline_severity: string | null;
  proposed_severity: string | null;
  capability_id: string | null;
  engineer_id: string | null;
  message: string;
};

export type CapabilityCoverageChange = {
  change_type: SimulationChangeType;
  capability_id: string;
  capability_name: string;
  baseline_level: string;
  proposed_level: string;
  baseline_effective_score: number;
  proposed_effective_score: number;
  score_delta: number;
  affected_engineer_ids: string[];
  is_critical: boolean;
};

export type KeyPersonDependencyChange = {
  change_type: SimulationChangeType;
  capability_id: string;
  capability_name: string;
  baseline_covering_engineer_ids: string[];
  proposed_covering_engineer_ids: string[];
  baseline_is_dependency: boolean;
  proposed_is_dependency: boolean;
  is_critical: boolean;
};

export type DecisionTraceDelta = {
  trace_key: string;
  step: string;
  component: string;
  label: string;
  baseline_contribution: number;
  proposed_contribution: number;
  contribution_delta: number;
  baseline_value: string;
  proposed_value: string;
};

export type DeterministicMitigation = {
  mitigation_id: string;
  mitigation_type: MitigationType;
  priority: MitigationPriority;
  title: string;
  action: string;
  rationale: string;
  capability_id: string | null;
  affected_engineer_ids: string[];
  evidence_references: string[];
  policy_version: string;
};

export type SimulationResponse = {
  simulation_id: string;
  project_id: string;
  operation: SimulationOperation;
  baseline_team: EngineerProfile[];
  proposed_team: EngineerProfile[];
  baseline_assessment: ReadinessAssessResponse;
  proposed_assessment: ReadinessAssessResponse;
  readiness_score_delta: number;
  confidence_delta: number;
  risk_level_changes: RiskFindingChange[];
  capability_coverage_changes: CapabilityCoverageChange[];
  newly_introduced_gaps: SkillGap[];
  resolved_gaps: SkillGap[];
  key_person_dependency_changes: KeyPersonDependencyChange[];
  decision_trace_delta: DecisionTraceDelta[];
  recommended_mitigations: DeterministicMitigation[];
  policy_version: string;
};

export function isSimulationOperation(value: unknown): value is SimulationOperation {
  if (!value || typeof value !== "object") return false;
  const op = value as { type?: string };
  switch (op.type) {
    case "add":
      return typeof (value as AddSimulationOperation).engineer_id === "string";
    case "remove":
      return typeof (value as RemoveSimulationOperation).engineer_id === "string";
    case "replace": {
      const replace = value as ReplaceSimulationOperation;
      return (
        typeof replace.remove_engineer_id === "string" &&
        typeof replace.add_engineer_id === "string"
      );
    }
    case "compare":
      return Array.isArray((value as CompareSimulationOperation).proposed_engineer_ids);
    default:
      return false;
  }
}

export type SimulationOperationTypeLabel = "add" | "remove" | "replace" | "compare";
