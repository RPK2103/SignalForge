import { Users } from "lucide-react";

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
import { demoScenario, teamRecommendation } from "@/lib/demo-data";
import { scoreBadgeClass, scoreValueClass } from "@/lib/score-colors";
import { cn } from "@/lib/utils";

export function TeamRecommendationCard() {
  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Team Recommendation</CardTitle>
            <CardDescription className="text-xs">
              Optimal roster for {demoScenario.project}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-sky-50 text-sky-600">
            <Users className="size-4" />
          </div>
        </div>
      </CardHeader>
      <CardContent className={cn(dashboardCardContentClass, "space-y-4")}>
        <ul className="divide-y rounded-md border">
          {teamRecommendation.members.map((member) => (
            <li
              key={member.name}
              className="flex items-center justify-between gap-3 px-3 py-2.5"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium">{member.name}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {member.role}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs text-muted-foreground">Fit:</span>
                <Badge
                  className={cn(
                    "tabular-nums text-white",
                    scoreBadgeClass(member.score)
                  )}
                >
                  {member.score}
                </Badge>
              </div>
            </li>
          ))}
        </ul>

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-md border bg-muted/30 p-3">
            <p className="text-xs text-muted-foreground">Team Status</p>
            <p className="mt-0.5 text-sm font-semibold text-emerald-700">
              {teamRecommendation.teamStatus}
            </p>
          </div>
          <div className="rounded-md border bg-muted/30 p-3">
            <p className="text-xs text-muted-foreground">Coverage Score</p>
            <p
              className={cn(
                "mt-0.5 text-sm font-semibold tabular-nums",
                scoreValueClass(teamRecommendation.coverageScore)
              )}
            >
              {teamRecommendation.coverageScore}%
            </p>
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Team Coverage</p>
          <div className="flex flex-wrap gap-1.5">
            {teamRecommendation.coverage.map((skill) => (
              <Badge key={skill} variant="outline">
                {skill}
              </Badge>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
