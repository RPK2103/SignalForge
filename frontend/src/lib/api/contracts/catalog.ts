import type {
  CapabilityCategory,
  CoverageLevel,
  EvidenceSource,
  ReadinessDimension,
  RiskFindingType,
  RiskSeverity,
} from "./enums";

export type CapabilityDefinition = {
  id: string;
  name: string;
  category: CapabilityCategory;
  keywords: string[];
};

export type EngineerCapability = {
  capability_id: string;
  proficiency: number;
  evidence_sources: EvidenceSource[];
};

export type EngineerProfile = {
  id: string;
  name: string;
  experience_years: number;
  capabilities: EngineerCapability[];
  has_certifications: boolean;
  has_project_history: boolean;
};

export type ProjectRequirement = {
  capability_id: string;
  weight: number;
  critical: boolean;
};

export type ProjectProfile = {
  id: string;
  name: string;
  requirements: ProjectRequirement[];
};

export type ReadinessPolicyMetadata = {
  version: string;
  description: string;
  dimension_weights: Record<string, number>;
  confidence_level_thresholds: Record<string, number>;
};

export type CapabilityListResponse = {
  capabilities: CapabilityDefinition[];
};

export type EngineerListResponse = {
  engineers: EngineerProfile[];
};

export type ProjectListResponse = {
  projects: ProjectProfile[];
};

export type ReadinessPolicyListResponse = {
  policies: ReadinessPolicyMetadata[];
  default_version: string;
};

export type CoverageResult = {
  capability_id: string;
  capability_name: string;
  category: CapabilityCategory;
  level: CoverageLevel;
  team_proficiency: number;
  covering_engineer_ids: string[];
  is_critical: boolean;
  weight: number;
};

export type SkillGap = {
  capability_id: string;
  capability_name: string;
  category: CapabilityCategory;
  level: CoverageLevel;
  is_critical: boolean;
  weight: number;
  covering_engineer_count: number;
};

export type RiskFinding = {
  finding_type: RiskFindingType;
  severity: RiskSeverity;
  capability_id: string | null;
  engineer_id: string | null;
  message: string;
};

export type ReadinessDimensionScore = {
  dimension: ReadinessDimension;
  score: number;
  weight: number;
};

export type DecisionTraceEntry = {
  step: string;
  component: string;
  label: string;
  value: string;
  contribution: number;
  policy_version: string;
};

export type ReadinessAssessRequest = {
  project_id: string;
  engineer_ids: string[];
  policy_version?: string | null;
};

export type ReadinessAssessResponse = {
  project_id: string;
  project_name: string;
  assessment_id: string;
  readiness_score: number;
  confidence_score: number;
  confidence_level: string;
  coverage_results: CoverageResult[];
  skill_gaps: SkillGap[];
  risk_findings: RiskFinding[];
  dimension_scores: ReadinessDimensionScore[];
  decision_trace: DecisionTraceEntry[];
  policy_version: string;
  summary: string;
  team: EngineerProfile[];
};
