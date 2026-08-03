import { apiClient } from "../client";
import type {
  AlertEvent,
  ObservabilitySummary,
} from "../contracts/observability";

const PREFIX = "/api/v3/observability";

export const observabilityService = {
  getSummary(options?: { signal?: AbortSignal }) {
    return apiClient.get<ObservabilitySummary>(`${PREFIX}/summary`, {
      signal: options?.signal,
    });
  },
  listOpenAlerts(options?: { signal?: AbortSignal }) {
    return apiClient.get<AlertEvent[]>(`${PREFIX}/alerts?state=open&limit=50`, {
      signal: options?.signal,
    });
  },
  acknowledgeAlert(alertId: string, options?: { signal?: AbortSignal }) {
    return apiClient.postNoBody<AlertEvent>(
      `${PREFIX}/alerts/${encodeURIComponent(alertId)}/acknowledge`,
      { signal: options?.signal }
    );
  },
};
