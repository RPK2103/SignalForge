import { apiClient } from "../client";
import type {
  CreateSimulationRecordRequest,
  SimulationHistoryResponse,
  SimulationRecordResponse,
} from "../contracts/simulation-records";

const SIMULATION_RECORDS_PREFIX = "/api/v2/simulation-records";

export type SimulationListParams = {
  project_id?: string;
  limit?: number;
  offset?: number;
};

function buildQuery(params: SimulationListParams): string {
  const search = new URLSearchParams();
  if (params.project_id) search.set("project_id", params.project_id);
  if (params.limit !== undefined) search.set("limit", String(params.limit));
  if (params.offset !== undefined) search.set("offset", String(params.offset));
  const query = search.toString();
  return query ? `?${query}` : "";
}

export const simulationRecordService = {
  create(
    request: CreateSimulationRecordRequest,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.postJson<SimulationRecordResponse>(
      SIMULATION_RECORDS_PREFIX,
      request,
      { signal: options?.signal }
    );
  },

  list(params: SimulationListParams = {}, options?: { signal?: AbortSignal }) {
    return apiClient.get<SimulationHistoryResponse>(
      `${SIMULATION_RECORDS_PREFIX}${buildQuery(params)}`,
      { signal: options?.signal }
    );
  },

  getById(
    simulationRecordId: string,
    options?: { signal?: AbortSignal }
  ) {
    return apiClient.get<SimulationRecordResponse>(
      `${SIMULATION_RECORDS_PREFIX}/${simulationRecordId}`,
      { signal: options?.signal }
    );
  },
};
