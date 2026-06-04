import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { demoScenario } from "@/lib/demo-data";

export function DashboardHeader() {
  return (
    <header className="space-y-4 border-b border-border/60 pb-5">
      <div className="flex flex-wrap items-center gap-2.5">
        <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Sparkles className="size-4" />
        </div>
        <Badge variant="secondary" className="font-normal">
          Execution Intelligence
        </Badge>
      </div>
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
          SignalForge
        </h1>
        <p className="max-w-2xl text-base text-muted-foreground">
          Evidence-based execution intelligence for engineering leaders.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline" className="h-7 px-2.5 text-xs font-normal">
          Project: {demoScenario.project}
        </Badge>
        <Badge variant="outline" className="h-7 px-2.5 text-xs font-normal">
          Engineer: {demoScenario.engineer}
        </Badge>
      </div>
    </header>
  );
}
