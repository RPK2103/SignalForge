import { apiClient } from "../client";
import type { PageResponse } from "../contracts/enterprise";
import type {
  ScenarioDefinition,
  ScenarioResult,
  ScenarioRun,
} from "../contracts/scenarios";

const PREFIX = "/api/v3/scenarios";

export const scenarioService = {
  listScenarios(
    params: { limit?: number; offset?: number } = {},
    options?: { signal?: AbortSignal }
  ) {
    const limit = params.limit ?? 20;
    const offset = params.offset ?? 0;
    return apiClient.get<PageResponse<ScenarioDefinition>>(
      `${PREFIX}?limit=${limit}&offset=${offset}`,
      { signal: options?.signal }
    );
  },
  listRuns(
    scenarioId: string,
    params: { limit?: number; offset?: number } = {},
    options?: { signal?: AbortSignal }
  ) {
    const limit = params.limit ?? 20;
    const offset = params.offset ?? 0;
    return apiClient.get<PageResponse<ScenarioRun>>(
      `${PREFIX}/${encodeURIComponent(scenarioId)}/runs?limit=${limit}&offset=${offset}`,
      { signal: options?.signal }
    );
  },
  getRunResult(runId: string, options?: { signal?: AbortSignal }) {
    return apiClient.get<ScenarioResult>(
      `${PREFIX}/runs/${encodeURIComponent(runId)}/result`,
      { signal: options?.signal }
    );
  },
};
