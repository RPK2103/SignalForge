import type {
  GenerationStatus,
  LeadershipActionPriority,
  LeadershipBriefFailureCategory,
  LeadershipBriefRiskSeverity,
  LeadershipDecision,
  ProviderMode,
} from "./enums";

export type LeadershipBriefRisk = {
  title: string;
  explanation: string;
  severity: LeadershipBriefRiskSeverity;
  evidence_references: string[];
};

export type LeadershipBriefAction = {
  title: string;
  action: string;
  rationale: string;
  priority: LeadershipActionPriority;
  capability_id: string | null;
  engineer_ids: string[];
  evidence_references: string[];
};

export type LeadershipBrief = {
  executive_summary: string;
  decision: LeadershipDecision;
  top_risks: LeadershipBriefRisk[];
  staffing_actions: LeadershipBriefAction[];
  mitigation_actions: LeadershipBriefAction[];
  confidence_statement: string;
  evidence_references: string[];
  provider_mode: ProviderMode;
  prompt_version: string;
  generation_status: GenerationStatus;
};

export type LeadershipBriefResponse = {
  leadership_brief_record_id: string;
  assessment_record_id: string;
  assessment_id: string;
  evidence_package_hash: string;
  output_snapshot_hash: string;
  failure_category: LeadershipBriefFailureCategory | null;
  created_at: string;
  brief: LeadershipBrief;
};

export type LeadershipBriefHistoryResponse = LeadershipBriefResponse[];

export function providerModeLabel(mode: ProviderMode): string {
  switch (mode) {
    case "azure_openai":
      return "AI-generated from deterministic SignalForge evidence";
    case "deterministic_fallback":
      return "Deterministic fallback brief";
    default:
      return mode;
  }
}

export function failureCategoryLabel(
  category: LeadershipBriefFailureCategory | null
): string | null {
  if (!category) return null;
  return category.replace(/_/g, " ");
}
