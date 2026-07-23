import { apiClient } from "../client";
import type {
  SimulationRequest,
  SimulationResponse,
} from "../contracts/simulations";

export const simulationService = {
  run(request: SimulationRequest, options?: { signal?: AbortSignal }) {
    return apiClient.postJson<SimulationResponse>(
      "/api/v2/simulations",
      request,
      { signal: options?.signal }
    );
  },
};
