import type { HumanReviewState } from "./enums";
import type { ReadinessAssessResponse } from "./catalog";

export type AssessmentRecordResponse = {
  assessment_record_id: string;
  assessment_id: string;
  project_id: string;
  policy_version: string;
  schema_version: string;
  created_at: string;
  input_snapshot_hash: string;
  result_snapshot_hash: string;
  result: ReadinessAssessResponse;
  latest_review_state: HumanReviewState | null;
  reviews: HumanReviewRecord[];
};

export type AssessmentHistoryItem = {
  assessment_record_id: string;
  assessment_id: string;
  project_id: string;
  readiness_score: number;
  confidence_score: number;
  confidence_level: string;
  policy_version: string;
  created_at: string;
  latest_review_state: HumanReviewState | null;
};

export type AssessmentHistoryResponse = {
  items: AssessmentHistoryItem[];
  total: number;
  limit: number;
  offset: number;
};

export type HumanReviewRecord = {
  review_id: string;
  assessment_record_id: string;
  state: HumanReviewState;
  override_reason: string | null;
  comment: string | null;
  reviewer_reference: string | null;
  created_at: string;
  schema_version: string;
};

export type CreateAssessmentRequest = {
  project_id: string;
  engineer_ids: string[];
  policy_version?: string | null;
};
