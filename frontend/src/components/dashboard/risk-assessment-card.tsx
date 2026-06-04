import { ShieldCheck } from "lucide-react";

import {
  dashboardCardClass,
  dashboardCardContentClass,
  dashboardCardHeaderClass,
} from "@/components/dashboard/dashboard-card-styles";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { demoScenario, riskAssessment } from "@/lib/demo-data";
import { cn } from "@/lib/utils";

export function RiskAssessmentCard() {
  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Risk Assessment</CardTitle>
            <CardDescription className="text-xs">
              Delivery risk for {demoScenario.project}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-emerald-50 text-emerald-600">
            <ShieldCheck className="size-4" />
          </div>
        </div>
      </CardHeader>
      <CardContent className={cn(dashboardCardContentClass, "space-y-4")}>
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Risk Score</p>
            <p className="text-3xl font-semibold tracking-tight tabular-nums text-emerald-700">
              {riskAssessment.riskScore}
            </p>
          </div>
          <Badge
            variant="outline"
            className="h-7 border-emerald-200 bg-emerald-50 px-3 text-sm text-emerald-700"
          >
            {riskAssessment.riskLevel} Risk
          </Badge>
        </div>
        <div className="rounded-md border bg-muted/40 p-3">
          <p className="mb-1 text-sm font-medium">Mitigation Plan</p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {riskAssessment.mitigationPlan}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
