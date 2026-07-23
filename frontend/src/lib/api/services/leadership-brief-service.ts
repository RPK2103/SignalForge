import { apiClient } from "../client";
import type { LeadershipBriefResponse } from "../contracts/leadership-briefs";

export const leadershipBriefService = {
  generate(
    assessmentRecordId: string,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.postNoBody<LeadershipBriefResponse>(
      `/api/v2/assessments/${assessmentRecordId}/leadership-brief`,
      { signal: options?.signal, timeoutMs: 120_000 }
    );
  },

  list(
    assessmentRecordId: string,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.get<LeadershipBriefResponse[]>(
      `/api/v2/assessments/${assessmentRecordId}/leadership-briefs`,
      { signal: options?.signal }
    );
  },
};
