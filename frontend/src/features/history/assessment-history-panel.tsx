"use client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/async-state";
import type {
  AssessmentHistoryItem,
  AssessmentRecordResponse,
} from "@/lib/api/contracts/assessments";
import { formatDateTime } from "@/lib/display-formatters";

type AssessmentHistoryPanelProps = {
  items: AssessmentHistoryItem[];
  total: number;
  selectedRecord: AssessmentRecordResponse | null;
  isLoading: boolean;
  isDetailLoading: boolean;
  errorMessage?: string | null;
  detailErrorMessage?: string | null;
  onRetry: () => void;
  onSelect: (recordId: string) => void;
  onLoadMore?: () => void;
  hasMore?: boolean;
  onOpenReview: () => void;
  isPersistedView?: boolean;
};

export function AssessmentHistoryPanel({
  items,
  total,
  selectedRecord,
  isLoading,
  isDetailLoading,
  errorMessage,
  detailErrorMessage,
  onRetry,
  onSelect,
  onLoadMore,
  hasMore = false,
  onOpenReview,
  isPersistedView = false,
}: AssessmentHistoryPanelProps) {
  if (isLoading) {
    return <LoadingState title="Loading assessment history" />;
  }

  if (errorMessage) {
    return (
      <ErrorState
        title="Assessment history unavailable"
        message={errorMessage}
        onRetry={onRetry}
      />
    );
  }

  if (items.length === 0) {
    return (
      <EmptyState
        title="No saved assessments"
        message="Run and save an assessment to build history."
      />
    );
  }

  return (
    <section aria-label="Assessment history" className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Assessment History</h3>
          <span className="text-xs text-muted-foreground">{total} total</span>
        </div>
        <ul className="space-y-2">
          {items.map((item) => (
            <li key={item.assessment_record_id}>
              <button
                type="button"
                onClick={() => onSelect(item.assessment_record_id)}
                className="w-full rounded-md border px-3 py-2 text-left hover:bg-muted/40"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{item.project_id}</span>
                  <span className="text-xs tabular-nums text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-2 text-xs">
                  <span>Readiness {item.readiness_score}</span>
                  <span>Confidence {item.confidence_score}</span>
                  {item.latest_review_state ? (
                    <Badge variant="outline">{item.latest_review_state}</Badge>
                  ) : null}
                </div>
              </button>
            </li>
          ))}
        </ul>
        {hasMore && onLoadMore ? (
          <Button type="button" variant="outline" size="sm" onClick={onLoadMore}>
            Load more
          </Button>
        ) : null}
      </div>

      <div className="rounded-lg border p-4">
        <h3 className="text-sm font-semibold">Assessment Detail</h3>
        {isDetailLoading ? (
          <LoadingState title="Loading assessment detail" className="mt-3" />
        ) : detailErrorMessage ? (
          <ErrorState
            title="Unable to load detail"
            message={detailErrorMessage}
            className="mt-3"
          />
        ) : !selectedRecord ? (
          <EmptyState
            title="Select an assessment"
            message="Open a saved assessment to view its immutable snapshot."
            className="mt-3"
          />
        ) : (
          <div className="mt-3 space-y-3 text-sm">
            <p>
              Record ID:{" "}
              <span className="break-all font-mono text-xs">
                {selectedRecord.assessment_record_id}
              </span>
            </p>
            <p>
              Deterministic ID:{" "}
              <span className="break-all font-mono text-xs">
                {selectedRecord.assessment_id}
              </span>
            </p>
            <p>
              Readiness {selectedRecord.result.readiness_score} · Confidence{" "}
              {selectedRecord.result.confidence_score} (
              {selectedRecord.result.confidence_level})
            </p>
            <p className="text-muted-foreground">{selectedRecord.result.summary}</p>
            {isPersistedView ? (
              <Badge variant="secondary">Persisted snapshot (not recomputed)</Badge>
            ) : null}
            {selectedRecord.reviews.length > 0 ? (
              <div className="space-y-2">
                <p className="font-medium">Review history</p>
                <ul className="space-y-1 text-xs">
                  {selectedRecord.reviews.map((review) => (
                    <li key={review.review_id} className="rounded border p-2">
                      {review.state} · {formatDateTime(review.created_at)}
                      {review.comment ? ` — ${review.comment}` : ""}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            <Button type="button" size="sm" onClick={onOpenReview}>
              Submit human review
            </Button>
            <details className="text-xs text-muted-foreground">
              <summary className="cursor-pointer">Audit metadata</summary>
              <p className="mt-2 break-all">
                Input hash: {selectedRecord.input_snapshot_hash}
              </p>
              <p className="break-all">
                Result hash: {selectedRecord.result_snapshot_hash}
              </p>
            </details>
          </div>
        )}
      </div>
    </section>
  );
}
