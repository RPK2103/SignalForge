"use client";

import { Badge } from "@/components/ui/badge";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/async-state";
import type { LeadershipBriefResponse } from "@/lib/api/contracts/leadership-briefs";
import {
  failureCategoryLabel,
  providerModeLabel,
} from "@/lib/api/contracts/leadership-briefs";
import { formatDateTime } from "@/lib/display-formatters";

type LeadershipBriefPanelProps = {
  briefs: LeadershipBriefResponse[];
  selectedBrief: LeadershipBriefResponse | null;
  isLoading: boolean;
  errorMessage?: string | null;
  onSelect: (briefId: string) => void;
  onRetry?: () => void;
};

export function LeadershipBriefPanel({
  briefs,
  selectedBrief,
  isLoading,
  errorMessage,
  onSelect,
  onRetry,
}: LeadershipBriefPanelProps) {
  if (isLoading) {
    return <LoadingState title="Loading Leadership Brief history" />;
  }

  if (errorMessage) {
    return (
      <ErrorState
        title="Leadership Brief history unavailable"
        message={errorMessage}
        onRetry={onRetry}
      />
    );
  }

  if (briefs.length === 0) {
    return (
      <EmptyState
        title="No Leadership Briefs yet"
        message="Generate a brief from a persisted assessment."
      />
    );
  }

  const brief = selectedBrief ?? briefs[0];

  return (
    <section aria-label="Leadership Brief history" className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-2 rounded-lg border p-4">
        <h3 className="text-sm font-semibold">Brief history</h3>
        <ul className="space-y-2">
          {briefs.map((item) => (
            <li key={item.leadership_brief_record_id}>
              <button
                type="button"
                onClick={() => onSelect(item.leadership_brief_record_id)}
                className="w-full rounded-md border px-3 py-2 text-left hover:bg-muted/40"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="outline">
                    {providerModeLabel(item.brief.provider_mode)}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </span>
                </div>
                {item.failure_category ? (
                  <p className="mt-1 text-xs text-amber-800">
                    {failureCategoryLabel(item.failure_category)}
                  </p>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="space-y-3 rounded-lg border p-4 text-sm">
        <h3 className="font-semibold">Brief detail</h3>
        <p className="text-xs text-muted-foreground">
          Advisory communication only. Scores remain deterministic.
        </p>
        <p>{brief.brief.executive_summary}</p>
        <p>
          Decision: <span className="capitalize">{brief.brief.decision.replace(/_/g, " ")}</span>
        </p>
        <p>{brief.brief.confidence_statement}</p>

        {brief.brief.top_risks.length > 0 ? (
          <div>
            <p className="font-medium">Top risks</p>
            <ul className="mt-1 space-y-1">
              {brief.brief.top_risks.map((risk) => (
                <li key={risk.title} className="rounded border p-2">
                  <p className="font-medium">{risk.title}</p>
                  <p className="text-muted-foreground">{risk.explanation}</p>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Evidence references</summary>
          <ul className="mt-2 space-y-1">
            {brief.brief.evidence_references.map((ref) => (
              <li key={ref} className="break-all font-mono">
                {ref}
              </li>
            ))}
          </ul>
          <p className="mt-2 break-all">Evidence hash: {brief.evidence_package_hash}</p>
          <p className="break-all">Output hash: {brief.output_snapshot_hash}</p>
        </details>
      </div>
    </section>
  );
}
