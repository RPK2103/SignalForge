import type { LeadershipBriefResponse } from "@/lib/api/contracts/leadership-briefs";
import {
  failureCategoryLabel,
  providerModeLabel,
} from "@/lib/api/contracts/leadership-briefs";
import { Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/async-state";

type AiExecutiveInsightProps = {
  brief: LeadershipBriefResponse | null;
  isGenerating?: boolean;
  canGenerate?: boolean;
  onGenerate?: () => void;
  assessmentRecordId?: string | null;
};

export function AiExecutiveInsight({
  brief,
  isGenerating = false,
  canGenerate = false,
  onGenerate,
  assessmentRecordId,
}: AiExecutiveInsightProps) {
  const providerMode = brief?.brief.provider_mode;
  const isFallback = providerMode === "deterministic_fallback";

  return (
    <Card className="border border-blue-200/80 bg-blue-50/40 shadow-sm">
      <CardHeader className="border-b border-blue-200/60 pb-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-blue-600 text-white">
              <Sparkles className="size-4" aria-hidden />
            </div>
            <CardTitle className="text-lg">Leadership Brief</CardTitle>
          </div>
          {providerMode ? (
            <Badge
              variant="outline"
              className={
                isFallback
                  ? "border-amber-200 bg-white/80 font-normal text-amber-800"
                  : "border-blue-200 bg-white/80 font-normal text-blue-700"
              }
            >
              {providerModeLabel(providerMode)}
            </Badge>
          ) : (
            <Badge
              variant="outline"
              className="border-blue-200 bg-white/80 font-normal text-blue-700"
            >
              Advisory communication layer
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-3">
        <p className="text-xs text-muted-foreground">
          Leadership Brief wording is advisory. Readiness and confidence scores
          remain deterministic and unchanged.
        </p>

        {!assessmentRecordId ? (
          <EmptyState
            title="Save an assessment to generate a Leadership Brief"
            message="Compute-only previews cannot generate briefs. Persist an assessment first."
          />
        ) : !brief && !isGenerating ? (
          <EmptyState
            title="No Leadership Brief yet"
            message={
              canGenerate
                ? "Generate a grounded brief from the persisted assessment evidence."
                : "Select a persisted assessment to generate a brief."
            }
          />
        ) : null}

        {isGenerating ? (
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
            Generating Leadership Brief… This may take a moment.
          </p>
        ) : null}

        {brief ? (
          <div className="space-y-3">
            {brief.failure_category ? (
              <p className="text-xs text-amber-800">
                Fallback reason: {failureCategoryLabel(brief.failure_category)}
              </p>
            ) : null}
            <p className="text-sm leading-relaxed text-foreground/90">
              {brief.brief.executive_summary}
            </p>
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
              <span>Decision: {brief.brief.decision.replace(/_/g, " ")}</span>
              <span>·</span>
              <span>Status: {brief.brief.generation_status.replace(/_/g, " ")}</span>
              <span>·</span>
              <span>Prompt: {brief.brief.prompt_version}</span>
            </div>
          </div>
        ) : null}

        {canGenerate && onGenerate ? (
          <button
            type="button"
            onClick={onGenerate}
            disabled={isGenerating}
            className="inline-flex h-9 items-center justify-center rounded-md bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {isGenerating ? "Generating…" : "Generate Leadership Brief"}
          </button>
        ) : null}
      </CardContent>
    </Card>
  );
}
