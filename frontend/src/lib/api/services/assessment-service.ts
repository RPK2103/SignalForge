import { apiClient } from "../client";
import type {
  AssessmentHistoryResponse,
  AssessmentRecordResponse,
  CreateAssessmentRequest,
} from "../contracts/assessments";

const ASSESSMENTS_PREFIX = "/api/v2/assessments";

export type AssessmentListParams = {
  project_id?: string;
  assessment_id?: string;
  review_state?: string;
  limit?: number;
  offset?: number;
};

function buildQuery(params: AssessmentListParams): string {
  const search = new URLSearchParams();
  if (params.project_id) search.set("project_id", params.project_id);
  if (params.assessment_id) search.set("assessment_id", params.assessment_id);
  if (params.review_state) search.set("review_state", params.review_state);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const query = search.toString();
  return query ? `?${query}` : "";
}

export const assessmentService = {
  create(
    request: CreateAssessmentRequest,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.postJson<AssessmentRecordResponse>(
      ASSESSMENTS_PREFIX,
      request,
      { signal: options?.signal }
    );
  },

  list(params: AssessmentListParams = {}, options?: { signal?: AbortSignal }) {
    return apiClient.get<AssessmentHistoryResponse>(
      `${ASSESSMENTS_PREFIX}${buildQuery(params)}`,
      { signal: options?.signal }
    );
  },

  getById(
    assessmentRecordId: string,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.get<AssessmentRecordResponse>(
      `${ASSESSMENTS_PREFIX}/${assessmentRecordId}`,
      { signal: options?.signal }
    );
  },
};
