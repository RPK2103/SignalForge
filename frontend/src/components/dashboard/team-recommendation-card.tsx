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
import { EmptyState } from "@/components/ui/async-state";
import type { EngineerProfile } from "@/lib/api/contracts/catalog";
import { scoreValueClass } from "@/lib/score-colors";
import { cn } from "@/lib/utils";

type TeamRecommendationCardProps = {
  projectName?: string | null;
  team?: EngineerProfile[];
  coverageScore?: number | null;
  coveredCapabilities?: string[];
};

export function TeamRecommendationCard({
  projectName,
  team = [],
  coverageScore = null,
  coveredCapabilities = [],
}: TeamRecommendationCardProps) {
  const teamStatus =
    team.length === 0
      ? "No team selected"
      : coverageScore !== null && coverageScore >= 90
        ? "Fully Staffed"
        : "Partial Coverage";

  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Selected Team</CardTitle>
            <CardDescription className="text-xs">
              {projectName
                ? `Team roster for ${projectName}`
                : "Engineers in current assessment"}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-sky-50 text-sky-600">
            <Users className="size-4" aria-hidden />
          </div>
        </div>
      </CardHeader>
      <CardContent className={cn(dashboardCardContentClass, "space-y-4")}>
        {team.length === 0 ? (
          <EmptyState
            title="No engineers selected"
            message="Select engineers from the catalog to build a team."
            className="border-0 bg-transparent px-0 py-2"
          />
        ) : (
          <>
            <ul className="divide-y rounded-md border">
              {team.map((member) => {
                return (
                  <li
                    key={member.id}
                    className="flex items-center justify-between gap-3 px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{member.name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {member.experience_years} yrs · {member.capabilities.length}{" "}
                        capabilities
                      </p>
                    </div>
                    <Badge variant="outline" className="shrink-0 tabular-nums">
                      {member.capabilities.length} caps
                    </Badge>
                  </li>
                );
              })}
            </ul>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs text-muted-foreground">Team Status</p>
                <p className="mt-0.5 text-sm font-semibold text-emerald-700">
                  {teamStatus}
                </p>
              </div>
              <div className="rounded-md border bg-muted/30 p-3">
                <p className="text-xs text-muted-foreground">Coverage Score (derived)</p>
                <p
                  className={cn(
                    "mt-0.5 text-sm font-semibold tabular-nums",
                    coverageScore !== null
                      ? scoreValueClass(coverageScore)
                      : "text-muted-foreground"
                  )}
                >
                  {coverageScore !== null ? `${coverageScore}%` : "—"}
                </p>
              </div>
            </div>

            {coveredCapabilities.length > 0 ? (
              <div className="space-y-2">
                <p className="text-sm font-medium">Team Coverage</p>
                <div className="flex flex-wrap gap-1.5">
                  {coveredCapabilities.map((skill) => (
                    <Badge key={skill} variant="outline">
                      {skill}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}
