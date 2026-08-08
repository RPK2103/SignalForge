export type ChiefOfStaffBriefRecord = {
  brief_id: string;
  tenant_id: string;
  run_id: string;
  evidence_snapshot_id: string;
  target_type: string;
  target_id: string;
  intent: string;
  as_of_at: string;
  horizon_days: number | null;
  brief_json: Record<string, unknown>;
  output_hash: string;
  output_schema_version: string;
  generation_state: string;
  final_provider: string;
  estimate_kind: string | null;
  probability: number | null;
  created_at: string;
};

export type ChiefOfStaffClaim = {
  claim_id: string;
  claim_type: string;
  text: string;
  support_status: string;
  authorship: string;
  temporal_cutoff: string;
  evidence_ids: string[];
  semantic_metadata?: Record<string, unknown>;
  ordering_index: number;
};

export type ChiefOfStaffCitation = {
  citation_id: string;
  claim_id: string;
  evidence_id: string;
  evidence_type: string;
  package_id: string;
  ordering_index: number;
};

export type QualitySummary = {
  tenant_id: string;
  total_runs: number;
  generated_count: number;
  fallback_count: number;
  fallback_rate: number;
  failed_count: number;
  rejected_count: number;
  failure_categories?: Record<string, number>;
  grounding_failures: number;
  citation_failures: number;
  unsupported_claim_detections: number;
  prompt_injection_detections?: number;
  provider_latency_ms_avg?: number | null;
  provider_latency_ms_max?: number | null;
  total_tokens_sum?: number | null;
};
