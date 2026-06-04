"use client";

import { Progress } from "@/components/ui/progress";
import { scoreIndicatorClass, scoreValueClass } from "@/lib/score-colors";
import { cn } from "@/lib/utils";

type ScoreBarProps = {
  label: string;
  score: number;
  className?: string;
};

export function ScoreBar({ label, score, className }: ScoreBarProps) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className={cn("font-medium tabular-nums", scoreValueClass(score))}>
          {score}
        </span>
      </div>
      <Progress
        value={score}
        className="h-1.5 bg-muted"
        indicatorClassName={scoreIndicatorClass(score)}
      />
    </div>
  );
}
