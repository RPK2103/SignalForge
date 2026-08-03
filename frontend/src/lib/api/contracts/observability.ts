export type ObservabilityHttpSummary = {
  request_total: number;
  server_error_total: number;
  server_error_rate: number | null;
  authentication_denials: number;
  authorization_denials: number;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
};

export type ObservabilityAiSummary = {
  fallback_rate: number | null;
  grounding_failure_rate: number | null;
  schema_valid_ratio: number | null;
};

export type SloStateSummary = {
  slo_key: string;
  indicator: string;
  status: "healthy" | "at_risk" | "breached" | "insufficient_data";
  observed_value: number | null;
  objective: number;
};

export type AiRunSummary = {
  id: string;
  status: string;
  aggregate_score: number | null;
  release_gate_passed: boolean | null;
  critical_violations: number;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  completed_at: string | null;
};

export type ObservabilitySummary = {
  telemetry_available: boolean;
  http: ObservabilityHttpSummary;
  ai: ObservabilityAiSummary;
  connectors: { success_ratio: number | null };
  slo_states: SloStateSummary[];
  open_alert_count: number;
  latest_ai_run: AiRunSummary | null;
  prediction_quality_available: boolean;
};

export type AlertEvent = {
  id: string;
  fingerprint: string;
  severity: "info" | "warning" | "critical";
  state: "open" | "acknowledged" | "resolved";
  source: string;
  title: string;
  reason_code: string;
  correlated_slo_key: string | null;
  opened_at: string;
  updated_at: string;
};
