import { apiClient } from "../client";
import type {
  ReadinessAssessRequest,
  ReadinessAssessResponse,
} from "../contracts/catalog";

const READINESS_PREFIX = "/api/v2/readiness";

export const readinessService = {
  assess(
    request: ReadinessAssessRequest,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.postJson<ReadinessAssessResponse>(
      `${READINESS_PREFIX}/assess`,
      request,
      { signal: options?.signal }
    );
  },
};
