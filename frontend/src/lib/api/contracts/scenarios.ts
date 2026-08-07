export type ScenarioDefinition = {
  scenario_definition_id: string;
  tenant_id: string;
  name: string;
  description: string;
  target_type: string;
  target_id: string;
  scenario_kind: string;
  lifecycle_state: string;
  current_version: number;
};

export type ScenarioRun = {
  scenario_run_id: string;
  tenant_id: string;
  scenario_definition_id: string;
  scenario_version_id: string;
  target_type: string;
  target_id: string;
  state: string;
  run_mode: string;
  as_of_at: string;
  horizon_days: number;
  created_at: string | null;
};

export type ScenarioResult = {
  scenario_result_id: string;
  scenario_run_id: string;
  tenant_id: string;
  target_type: string;
  target_id: string;
  as_of_at: string;
  horizon_days: number;
  scenario_kind: string;
  baseline_estimate_kind: string;
  simulated_estimate_kind: string;
  estimate_comparability: string;
  baseline_probability: number | null;
  simulated_probability: number | null;
  baseline_risk_score: number | null;
  simulated_risk_score: number | null;
  risk_score_delta: number | null;
  affected_project_count: number;
  affected_initiative_count: number;
  affected_critical_initiative_count: number;
  findings_added_count: number;
  findings_removed_count: number;
  findings_worsened_count: number;
  findings_improved_count: number;
  data_quality_warnings: string[];
  applicability_warnings: string[];
};
