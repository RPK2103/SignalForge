import { UserSearch } from "lucide-react";

import {
  dashboardCardClass,
  dashboardCardContentClass,
  dashboardCardHeaderClass,
} from "@/components/dashboard/dashboard-card-styles";
import { ScoreBar } from "@/components/dashboard/score-bar";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { EmptyState } from "@/components/ui/async-state";
import type { ReadinessDimensionScore } from "@/lib/api/contracts/catalog";
import { dimensionLabel } from "@/lib/display-formatters";

type EngineerAnalysisCardProps = {
  engineerName?: string | null;
  dimensionScores?: ReadinessDimensionScore[];
};

export function EngineerAnalysisCard({
  engineerName,
  dimensionScores = [],
}: EngineerAnalysisCardProps) {
  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Readiness Dimensions</CardTitle>
            <CardDescription className="text-xs">
              {engineerName
                ? `Team context: ${engineerName}`
                : "Deterministic dimension breakdown"}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600">
            <UserSearch className="size-4" aria-hidden />
          </div>
        </div>
      </CardHeader>
      <CardContent className={dashboardCardContentClass}>
        {dimensionScores.length === 0 ? (
          <EmptyState
            title="No dimension scores"
            message="Run an assessment to view readiness dimensions."
            className="border-0 bg-transparent px-0 py-2"
          />
        ) : (
          <div className="space-y-3">
            {dimensionScores.map((item) => (
              <ScoreBar
                key={item.dimension}
                label={dimensionLabel(item.dimension)}
                score={item.score}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
