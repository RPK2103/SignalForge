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
import { EmptyState } from "@/components/ui/async-state";
import type { RiskFinding } from "@/lib/api/contracts/catalog";
import { cn } from "@/lib/utils";

type RiskAssessmentCardProps = {
  projectName?: string | null;
  riskFindings?: RiskFinding[];
  mitigations?: Array<{ title: string; action: string }>;
};

function highestRiskLevel(findings: RiskFinding[]): string {
  if (findings.length === 0) return "Low";
  const order = { low: 0, medium: 1, high: 2 } as const;
  const max = findings.reduce((current, finding) => {
    const severity = finding.severity as keyof typeof order;
    return order[severity] > order[current] ? severity : current;
  }, "low" as keyof typeof order);
  return max.charAt(0).toUpperCase() + max.slice(1);
}

export function RiskAssessmentCard({
  projectName,
  riskFindings = [],
  mitigations = [],
}: RiskAssessmentCardProps) {
  const riskScore = riskFindings.length;
  const riskLevel = highestRiskLevel(riskFindings);
  const primaryMitigation = mitigations[0];

  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Risk Assessment</CardTitle>
            <CardDescription className="text-xs">
              {projectName
                ? `Delivery risk for ${projectName}`
                : "Deterministic risk findings"}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-emerald-50 text-emerald-600">
            <ShieldCheck className="size-4" aria-hidden />
          </div>
        </div>
      </CardHeader>
      <CardContent className={cn(dashboardCardContentClass, "space-y-4")}>
        {riskFindings.length === 0 ? (
          <EmptyState
            title="No risk findings"
            message="Run an assessment to view deterministic risk findings."
            className="border-0 bg-transparent px-0 py-2"
          />
        ) : (
          <>
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Risk Findings</p>
                <p className="text-3xl font-semibold tracking-tight tabular-nums text-foreground">
                  {riskFindings.length}
                </p>
              </div>
              <Badge
                variant="outline"
                className="h-7 border-emerald-200 bg-emerald-50 px-3 text-sm text-emerald-700"
              >
                {riskLevel} severity · {riskScore} finding{riskScore === 1 ? "" : "s"}
              </Badge>
            </div>
            <ul className="space-y-2">
              {riskFindings.slice(0, 4).map((finding, index) => (
                <li
                  key={`${finding.finding_type}-${finding.capability_id ?? ""}-${finding.engineer_id ?? ""}-${index}`}
                  className="rounded-md border bg-muted/40 p-3 text-sm"
                >
                  <p className="font-medium capitalize">
                    {finding.finding_type.replace(/_/g, " ")} ({finding.severity})
                  </p>
                  <p className="text-muted-foreground">{finding.message}</p>
                </li>
              ))}
            </ul>
            {primaryMitigation ? (
              <div className="rounded-md border bg-muted/40 p-3">
                <p className="mb-1 text-sm font-medium">Suggested Mitigation</p>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {primaryMitigation.action}
                </p>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
