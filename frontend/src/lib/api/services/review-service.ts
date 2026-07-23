import { apiClient } from "../client";
import type { HumanReviewRequest } from "../contracts/reviews";
import type { AssessmentRecordResponse } from "../contracts/assessments";

export const reviewService = {
  submit(
    assessmentRecordId: string,
    request: HumanReviewRequest,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.postJson<AssessmentRecordResponse>(
      `/api/v2/assessments/${assessmentRecordId}/reviews`,
      request,
      { signal: options?.signal }
    );
  },
};
