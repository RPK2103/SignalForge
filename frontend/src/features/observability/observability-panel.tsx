"use client";

import { useCallback, useEffect } from "react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/async-state";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAsyncRequest } from "@/hooks/use-async-request";
import { observabilityService } from "@/lib/api/services/observability-service";
import type {
  AlertEvent,
  ObservabilitySummary,
  SloStateSummary,
} from "@/lib/api/contracts/observability";

type PanelData = {
  summary: ObservabilitySummary;
  alerts: AlertEvent[];
};

function formatRatio(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function formatMs(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${value.toFixed(0)} ms`;
}

function sloBadgeVariant(
  status: SloStateSummary["status"]
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "breached") return "destructive";
  if (status === "at_risk") return "secondary";
  if (status === "healthy") return "default";
  return "outline";
}

function severityVariant(
  severity: AlertEvent["severity"]
): "default" | "secondary" | "destructive" | "outline" {
  if (severity === "critical") return "destructive";
  if (severity === "warning") return "secondary";
  return "outline";
}

function MetricTile({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-muted/10 px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export function ObservabilityPanel() {
  const { state, execute } = useAsyncRequest<PanelData>();

  const load = useCallback(() => {
    void execute(async (signal) => {
      const [summary, alerts] = await Promise.all([
        observabilityService.getSummary({ signal }),
        observabilityService.listOpenAlerts({ signal }),
      ]);
      return { summary, alerts };
    });
  }, [execute]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.status === "loading" || state.status === "idle") {
    return (
      <LoadingState
        title="Loading observability"
        message="Fetching operational health and AI-quality signals…"
      />
    );
  }

  if (state.status === "error") {
    const forbidden = state.error?.statusCode === 403;
    return (
      <ErrorState
        title={
          forbidden
            ? "You do not have access to observability"
            : "Could not load observability"
        }
        message={
          forbidden
            ? "This area requires the observability.read permission."
            : (state.errorMessage ?? "An unexpected error occurred.")
        }
        onRetry={forbidden ? undefined : load}
      />
    );
  }

  const data = state.data;
  if (!data) {
    return <EmptyState title="No observability data" />;
  }

  const { summary, alerts } = data;
  const run = summary.latest_ai_run;

  return (
    <div className="space-y-6" data-testid="observability-panel">
      <section aria-label="Request health">
        <Card>
          <CardHeader>
            <CardTitle>Request health</CardTitle>
            <CardDescription>
              Expected 401/403 are security denials — never counted as server
              failures.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <MetricTile
                label="Requests"
                value={summary.http.request_total.toLocaleString()}
              />
              <MetricTile
                label="5xx rate"
                value={formatRatio(summary.http.server_error_rate)}
              />
              <MetricTile
                label="p50 latency"
                value={formatMs(summary.http.latency_p50_ms)}
              />
              <MetricTile
                label="p95 latency"
                value={formatMs(summary.http.latency_p95_ms)}
              />
              <MetricTile
                label="Auth denials"
                value={summary.http.authentication_denials.toLocaleString()}
              />
              <MetricTile
                label="Authz denials"
                value={summary.http.authorization_denials.toLocaleString()}
              />
            </div>
          </CardContent>
        </Card>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section aria-label="AI quality">
          <Card className="h-full">
            <CardHeader>
              <CardTitle>AI quality</CardTitle>
              <CardDescription>Provider and grounding health.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <MetricTile
                  label="Fallback rate"
                  value={formatRatio(summary.ai.fallback_rate)}
                />
                <MetricTile
                  label="Grounding fail"
                  value={formatRatio(summary.ai.grounding_failure_rate)}
                />
                <MetricTile
                  label="Schema valid"
                  value={formatRatio(summary.ai.schema_valid_ratio)}
                />
              </div>
              <div className="rounded-lg border border-border/70 px-4 py-3">
                <p className="text-xs text-muted-foreground">
                  Latest evaluation run
                </p>
                {run ? (
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="text-sm tabular-nums">
                      {run.passed_cases}/{run.total_cases} passed
                    </span>
                    <Badge
                      variant={
                        run.release_gate_passed ? "default" : "destructive"
                      }
                    >
                      {run.release_gate_passed
                        ? "Gate passed"
                        : `Gate failed (${run.critical_violations})`}
                    </Badge>
                  </div>
                ) : (
                  <p className="mt-1 text-sm text-muted-foreground">
                    No evaluation run yet
                  </p>
                )}
              </div>
              <p className="text-xs text-muted-foreground">
                Connector success:{" "}
                {formatRatio(summary.connectors.success_ratio)} · Prediction
                quality:{" "}
                {summary.prediction_quality_available
                  ? "available"
                  : "unavailable"}
              </p>
            </CardContent>
          </Card>
        </section>

        <section aria-label="Service level objectives">
          <Card className="h-full">
            <CardHeader>
              <CardTitle>SLO status</CardTitle>
              <CardDescription>
                Deterministic evaluation over the configured window.
              </CardDescription>
            </CardHeader>
            <CardContent>
              {summary.slo_states.length === 0 ? (
                <EmptyState
                  title="No SLOs evaluated"
                  message="Run an SLO evaluation to populate status."
                />
              ) : (
                <ul className="space-y-2">
                  {summary.slo_states.map((slo) => (
                    <li
                      key={slo.slo_key}
                      className="flex items-center justify-between gap-2 rounded-md border border-border/60 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {slo.slo_key}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {slo.indicator}
                        </p>
                      </div>
                      <Badge variant={sloBadgeVariant(slo.status)}>
                        {slo.status}
                      </Badge>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </section>
      </div>

      <section aria-label="Open alerts">
        <Card>
          <CardHeader>
            <CardTitle>Open alerts ({summary.open_alert_count})</CardTitle>
            <CardDescription>
              Internal alert state only — no external delivery.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {alerts.length === 0 ? (
              <EmptyState
                title="No open alerts"
                message="All monitored conditions are healthy."
              />
            ) : (
              <ul className="space-y-2">
                {alerts.map((alert) => (
                  <li
                    key={alert.id}
                    className="flex items-center justify-between gap-2 rounded-md border border-border/60 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {alert.title}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {alert.reason_code}
                      </p>
                    </div>
                    <Badge variant={severityVariant(alert.severity)}>
                      {alert.severity}
                    </Badge>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
