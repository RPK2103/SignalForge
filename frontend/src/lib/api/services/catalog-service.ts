import { apiClient } from "../client";
import type {
  CapabilityListResponse,
  EngineerListResponse,
  ProjectListResponse,
  ReadinessPolicyListResponse,
} from "../contracts/catalog";

const CATALOG_PREFIX = "/api/v2";

export const catalogService = {
  listProjects(options?: { signal?: AbortSignal }) {
    return apiClient.get<ProjectListResponse>(`${CATALOG_PREFIX}/projects`, {
      signal: options?.signal,
    });
  },

  listEngineers(options?: { signal?: AbortSignal }) {
    return apiClient.get<EngineerListResponse>(`${CATALOG_PREFIX}/engineers`, {
      signal: options?.signal,
    });
  },

  listCapabilities(options?: { signal?: AbortSignal }) {
    return apiClient.get<CapabilityListResponse>(
      `${CATALOG_PREFIX}/capabilities`,
      { signal: options?.signal }
    );
  },

  listReadinessPolicies(options?: { signal?: AbortSignal }) {
    return apiClient.get<ReadinessPolicyListResponse>(
      `${CATALOG_PREFIX}/policies/readiness`,
      { signal: options?.signal }
    );
  },
};
