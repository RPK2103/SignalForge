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
import { demoScenario, projectFit } from "@/lib/demo-data";
import { scoreBadgeClass, scoreValueClass } from "@/lib/score-colors";
import { cn } from "@/lib/utils";

export function ProjectFitCard() {
  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Project Fit Recommendation</CardTitle>
            <CardDescription className="text-xs">
              Alignment with {demoScenario.project}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-violet-50 text-violet-600">
            <Target className="size-4" />
          </div>
        </div>
      </CardHeader>
      <CardContent className={cn(dashboardCardContentClass, "space-y-4")}>
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-xs text-muted-foreground">Fit Score</p>
            <p
              className={cn(
                "text-3xl font-semibold tracking-tight tabular-nums",
                scoreValueClass(projectFit.fitScore)
              )}
            >
              {projectFit.fitScore}
            </p>
          </div>
          <Badge
            className={cn(
              "h-7 px-3 text-sm text-white",
              scoreBadgeClass(projectFit.fitScore)
            )}
          >
            {projectFit.recommendation}
          </Badge>
        </div>
        <div className="space-y-2">
          <p className="text-sm font-medium">Matched Skills</p>
          <div className="flex flex-wrap gap-1.5">
            {projectFit.matchedSkills.map((skill) => (
              <Badge key={skill} variant="secondary">
                {skill}
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
