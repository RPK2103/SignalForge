import { Activity, Gauge, Shield, Target } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { executiveSummary } from "@/lib/demo-data";
import { cn } from "@/lib/utils";

const kpiIcons = [Target, Shield, Activity, Gauge] as const;

function kpiValueClass(value: string): string {
  if (value === "Low") return "text-emerald-700";
  if (value.includes("%") || value === "100") return "text-emerald-700";
  return "text-foreground";
}

export function ExecutiveSummary() {
  return (
    <section aria-label="Execution intelligence summary" className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-xl font-semibold tracking-tight">
          Execution Intelligence Summary
        </h2>
        <p className="text-sm text-muted-foreground">
          AI-powered staffing and delivery confidence assessment.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {executiveSummary.kpis.map((kpi, index) => {
          const Icon = kpiIcons[index];
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

      <div className="rounded-lg border border-border/70 bg-muted/30 px-4 py-3">
        <div className="mb-1 flex items-center gap-2">
          <Badge variant="secondary" className="font-normal">
            Executive Insight
          </Badge>
        </div>
        <p className="text-sm leading-relaxed text-foreground/90">
          {executiveSummary.insight}
        </p>
      </div>
    </section>
  );
}
