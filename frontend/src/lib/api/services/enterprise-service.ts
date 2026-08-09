import { apiClient } from "../client";
import type {
  DemoTenantSummary,
  GraphFinding,
  GraphSummary,
  Initiative,
  Organization,
  PageResponse,
} from "../contracts/enterprise";

const PREFIX = "/api/v3";

export const enterpriseService = {
  getOrganization(options?: { signal?: AbortSignal }) {
    return apiClient.get<Organization>(`${PREFIX}/organization`, {
      signal: options?.signal,
    });
  },
  getDemoSummary(options?: { signal?: AbortSignal }) {
    return apiClient.get<DemoTenantSummary>(`${PREFIX}/demo/summary`, {
      signal: options?.signal,
    });
  },
  listInitiatives(
    params: { limit?: number; offset?: number } = {},
    options?: { signal?: AbortSignal }
  ) {
    const limit = params.limit ?? 20;
    const offset = params.offset ?? 0;
    return apiClient.get<PageResponse<Initiative>>(
      `${PREFIX}/initiatives?limit=${limit}&offset=${offset}`,
      { signal: options?.signal }
    );
  },
  getGraphSummary(options?: { signal?: AbortSignal }) {
    return apiClient.get<GraphSummary>(`${PREFIX}/delivery-graph/summary`, {
      signal: options?.signal,
    });
  },
  listFindings(
    params: { limit?: number; offset?: number } = {},
    options?: { signal?: AbortSignal }
  ) {
    const limit = params.limit ?? 20;
    const offset = params.offset ?? 0;
    return apiClient.get<PageResponse<GraphFinding>>(
      `${PREFIX}/delivery-graph/findings?limit=${limit}&offset=${offset}`,
      { signal: options?.signal }
    );
  },
};
