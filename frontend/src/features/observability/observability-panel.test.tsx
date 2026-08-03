import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

import { ObservabilityPanel } from "@/features/observability/observability-panel";
import { SignalForgeApiError } from "@/lib/api/errors";
import { observabilityService } from "@/lib/api/services/observability-service";
import type { ObservabilitySummary } from "@/lib/api/contracts/observability";

vi.mock("@/lib/api/services/observability-service", () => ({
  observabilityService: {
    getSummary: vi.fn(),
    listOpenAlerts: vi.fn(),
    acknowledgeAlert: vi.fn(),
  },
}));

const mockedService = vi.mocked(observabilityService);

function baseSummary(overrides: Partial<ObservabilitySummary> = {}): ObservabilitySummary {
  return {
    telemetry_available: true,
    http: {
      request_total: 120,
      server_error_total: 0,
      server_error_rate: 0,
      authentication_denials: 5,
      authorization_denials: 3,
      latency_p50_ms: 12,
      latency_p95_ms: 40,
    },
    ai: {
      fallback_rate: 0,
      grounding_failure_rate: 0,
      schema_valid_ratio: 1,
    },
    connectors: { success_ratio: 1 },
    slo_states: [
      {
        slo_key: "api_availability",
        indicator: "api_5xx_free_ratio",
        status: "healthy",
        observed_value: 1,
        objective: 0.99,
      },
    ],
    open_alert_count: 0,
    latest_ai_run: {
      id: "air_1",
      status: "completed",
      aggregate_score: 1,
      release_gate_passed: true,
      critical_violations: 0,
      total_cases: 13,
      passed_cases: 13,
      failed_cases: 0,
      completed_at: "2026-07-31T00:00:00Z",
    },
    prediction_quality_available: false,
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ObservabilityPanel", () => {
  it("renders metrics, SLO status and gate result on success", async () => {
    mockedService.getSummary.mockResolvedValue(baseSummary());
    mockedService.listOpenAlerts.mockResolvedValue([]);

    render(<ObservabilityPanel />);

    await waitFor(() =>
      expect(screen.getByTestId("observability-panel")).toBeInTheDocument()
    );
    expect(screen.getByText(/Request health/i)).toBeInTheDocument();
    expect(screen.getByText("api_availability")).toBeInTheDocument();
    expect(screen.getByText(/Gate passed/i)).toBeInTheDocument();
    expect(screen.getByText(/No open alerts/i)).toBeInTheDocument();
  });

  it("shows a forbidden message without retry on 403", async () => {
    mockedService.getSummary.mockRejectedValue(
      new SignalForgeApiError({
        message: "forbidden",
        category: "api_error",
        statusCode: 403,
      })
    );
    mockedService.listOpenAlerts.mockResolvedValue([]);

    render(<ObservabilityPanel />);

    await waitFor(() =>
      expect(
        screen.getByText(/do not have access to observability/i)
      ).toBeInTheDocument()
    );
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("shows an error with retry on a non-403 failure", async () => {
    mockedService.getSummary.mockRejectedValue(
      new SignalForgeApiError({
        message: "boom",
        category: "unknown_error",
        statusCode: 500,
      })
    );
    mockedService.listOpenAlerts.mockResolvedValue([]);

    render(<ObservabilityPanel />);

    await waitFor(() =>
      expect(screen.getByText(/Could not load observability/i)).toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("renders open alerts and gate-failed state", async () => {
    mockedService.getSummary.mockResolvedValue(
      baseSummary({
        open_alert_count: 1,
        latest_ai_run: {
          id: "air_2",
          status: "completed",
          aggregate_score: 0.8,
          release_gate_passed: false,
          critical_violations: 2,
          total_cases: 13,
          passed_cases: 11,
          failed_cases: 2,
          completed_at: null,
        },
      })
    );
    mockedService.listOpenAlerts.mockResolvedValue([
      {
        id: "al_1",
        fingerprint: "fp",
        severity: "critical",
        state: "open",
        source: "slo",
        title: "SLO api_availability breached",
        reason_code: "slo_breached",
        correlated_slo_key: "api_availability",
        opened_at: "2026-07-31T00:00:00Z",
        updated_at: "2026-07-31T00:00:00Z",
      },
    ]);

    render(<ObservabilityPanel />);

    await waitFor(() =>
      expect(
        screen.getByText(/SLO api_availability breached/i)
      ).toBeInTheDocument()
    );
    expect(screen.getByText(/Gate failed/i)).toBeInTheDocument();
  });
});
