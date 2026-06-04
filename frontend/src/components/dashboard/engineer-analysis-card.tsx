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
import { capabilityScores, demoScenario } from "@/lib/demo-data";

export function EngineerAnalysisCard() {
  return (
    <Card className={dashboardCardClass}>
      <CardHeader className={dashboardCardHeaderClass}>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-0.5">
            <CardTitle className="text-base">Engineer Analysis</CardTitle>
            <CardDescription className="text-xs">
              Capability profile for {demoScenario.engineer}
            </CardDescription>
          </div>
          <div className="flex size-8 shrink-0 items-center justify-center rounded-md bg-blue-50 text-blue-600">
            <UserSearch className="size-4" />
          </div>
        </div>
      </CardHeader>
      <CardContent className={dashboardCardContentClass}>
        <div className="space-y-3">
          {capabilityScores.map((item) => (
            <ScoreBar key={item.label} label={item.label} score={item.score} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
