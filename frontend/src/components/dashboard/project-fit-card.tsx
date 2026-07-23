import { Target } from "lucide-react";

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
import type { CoverageResult } from "@/lib/api/contracts/catalog";
import { scoreBadgeClass, scoreValueClass } from "@/lib/score-colors";
import { cn } from "@/lib/utils";

type ProjectFitCardProps = {
  projectName?: string | null;
  readinessScore?: number | null;
  coverageResults?: CoverageResult[];
};

export function ProjectFitCard({
  projectName,
  readinessScore = null,
  coverageResults = [],
}: ProjectFitCardProps) {
  const matchedSkills = coverageResults
    .filter((item) => item.level !== "missing")
    .map((item) => item.capability_name);

  const recommendation =
    readinessScore === null
      ? null
      : readinessScore >= 85
        ? "Strong Fit"
        : readinessScore >= 70
          ? "Moderate Fit"
          : "Limited Fit";

  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Capability Coverage</CardTitle>
            <CardDescription className="text-xs">
              {projectName
                ? `Coverage for ${projectName}`
                : "Project capability alignment"}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-violet-50 text-violet-600">
            <Target className="size-4" aria-hidden />
          </div>
        </div>
      </CardHeader>
      <CardContent className={cn(dashboardCardContentClass, "space-y-4")}>
        {readinessScore === null ? (
          <EmptyState
            title="No coverage data"
            message="Run an assessment to view capability coverage."
            className="border-0 bg-transparent px-0 py-2"
          />
        ) : (
          <>
            <div className="flex items-end justify-between gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Readiness Score</p>
                <p
                  className={cn(
                    "text-3xl font-semibold tracking-tight tabular-nums",
                    scoreValueClass(readinessScore)
                  )}
                >
                  {readinessScore}
                </p>
              </div>
              {recommendation ? (
                <Badge
                  className={cn(
                    "h-7 px-3 text-sm text-white",
                    scoreBadgeClass(readinessScore)
                  )}
                >
                  {recommendation}
                </Badge>
              ) : null}
            </div>
            <div className="space-y-2">
              <p className="text-sm font-medium">Covered Capabilities</p>
              {matchedSkills.length === 0 ? (
                <p className="text-sm text-muted-foreground">No covered capabilities.</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {matchedSkills.map((skill) => (
                    <Badge key={skill} variant="secondary">
                      {skill}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
