import { Activity, Gauge, Shield, Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/async-state";
import { cn } from "@/lib/utils";

const kpiIcons = [Target, Shield, Activity, Gauge] as const;

type ExecutiveSummaryProps = {
  kpis: Array<{ label: string; value: string }>;
  insight?: string | null;
  sourceLabel?: string;
};

function kpiValueClass(value: string): string {
  if (value.toLowerCase().includes("low")) return "text-emerald-700";
  if (value.includes("%") || value === "100") return "text-emerald-700";
  return "text-foreground";
}

export function ExecutiveSummary({
  kpis,
  insight,
  sourceLabel = "Deterministic Assessment",
}: ExecutiveSummaryProps) {
  if (kpis.length === 0) {
    return (
      <section aria-label="Execution intelligence summary" className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight">
            Execution Intelligence Summary
          </h2>
          <p className="text-sm text-muted-foreground">
            Select a project and team, then run an assessment.
          </p>
        </div>
        <EmptyState
          title="No assessment results yet"
          message="Run a readiness assessment to populate KPIs and insights."
        />
      </section>
    );
  }

  return (
    <section aria-label="Execution intelligence summary" className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold tracking-tight">
          Execution Intelligence Summary
        </h2>
        <p className="text-sm text-muted-foreground">
          Deterministic readiness and confidence from the SignalForge backend.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {kpis.map((kpi, index) => {
          const Icon = kpiIcons[index % kpiIcons.length];
          return (
            <Card
              key={kpi.label}
              className="border border-border/70 shadow-sm"
            >
              <CardContent className="flex items-start justify-between gap-2 p-4">
                <div className="min-w-0 space-y-1">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {kpi.label}
                  </p>
                  <p
                    className={cn(
                      "text-2xl font-semibold tabular-nums tracking-tight",
                      kpiValueClass(kpi.value)
                    )}
                  >
                    {kpi.value}
                  </p>
                </div>
                <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <Icon className="size-4" />
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      {insight ? (
        <div className="rounded-lg border border-border/70 bg-muted/30 px-4 py-3">
          <div className="mb-1 flex items-center gap-2">
            <Badge variant="secondary" className="font-normal">
              {sourceLabel}
            </Badge>
          </div>
          <p className="text-sm leading-relaxed text-foreground/90">{insight}</p>
        </div>
      ) : null}
    </section>
  );
}
