import { apiClient } from "../client";
import type { PageResponse } from "../contracts/enterprise";
import type {
  ChiefOfStaffBriefRecord,
  ChiefOfStaffCitation,
  ChiefOfStaffClaim,
  QualitySummary,
} from "../contracts/chief-of-staff";

const PREFIX = "/api/v3/chief-of-staff";

export const chiefOfStaffService = {
  listBriefs(
    params: { limit?: number; offset?: number } = {},
    options?: { signal?: AbortSignal }
  ) {
    const limit = params.limit ?? 20;
    const offset = params.offset ?? 0;
    return apiClient.get<PageResponse<ChiefOfStaffBriefRecord>>(
      `${PREFIX}/briefs?limit=${limit}&offset=${offset}`,
      { signal: options?.signal }
    );
  },
  getBrief(briefId: string, options?: { signal?: AbortSignal }) {
    return apiClient.get<ChiefOfStaffBriefRecord>(
      `${PREFIX}/briefs/${encodeURIComponent(briefId)}`,
      { signal: options?.signal }
    );
  },
  listClaims(briefId: string, options?: { signal?: AbortSignal }) {
    return apiClient.get<ChiefOfStaffClaim[]>(
      `${PREFIX}/briefs/${encodeURIComponent(briefId)}/claims`,
      { signal: options?.signal }
    );
  },
  listCitations(briefId: string, options?: { signal?: AbortSignal }) {
    return apiClient.get<ChiefOfStaffCitation[]>(
      `${PREFIX}/briefs/${encodeURIComponent(briefId)}/citations`,
      { signal: options?.signal }
    );
  },
  getQualitySummary(options?: { signal?: AbortSignal }) {
    return apiClient.get<QualitySummary>(`${PREFIX}/quality-summary`, {
      signal: options?.signal,
    });
  },
};
