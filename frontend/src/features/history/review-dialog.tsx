"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import type { HumanReviewState } from "@/lib/api/contracts/enums";

type ReviewDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: {
    state: HumanReviewState;
    comment?: string;
    override_reason?: string;
  }) => Promise<void>;
  isSubmitting?: boolean;
};

export function ReviewDialog({
  open,
  onOpenChange,
  onSubmit,
  isSubmitting = false,
}: ReviewDialogProps) {
  const [state, setState] = useState<HumanReviewState>("accepted");
  const [comment, setComment] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const resetForm = () => {
    setState("accepted");
    setComment("");
    setOverrideReason("");
    setValidationError(null);
  };

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      resetForm();
    }
    onOpenChange(nextOpen);
  };

  const handleSubmit = async () => {
    setValidationError(null);

    if (state === "overridden" && !overrideReason.trim()) {
      setValidationError("Override reason is required.");
      return;
    }

    if (state === "needs_more_data" && !comment.trim()) {
      setValidationError("Comment is required for needs more data.");
      return;
    }

    await onSubmit({
      state,
      comment: comment.trim() || undefined,
      override_reason: overrideReason.trim() || undefined,
    });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Submit human review</DialogTitle>
          <DialogDescription>
            Human review records an operational judgment. It does not rewrite
            deterministic readiness or confidence scores.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <label htmlFor="review-state" className="text-sm font-medium">
              Review state
            </label>
            <select
              id="review-state"
              value={state}
              onChange={(event) => {
                setState(event.target.value as HumanReviewState);
                setValidationError(null);
              }}
              className="h-10 w-full rounded-md border px-3 text-sm"
            >
              <option value="accepted">Accepted</option>
              <option value="overridden">Overridden</option>
              <option value="needs_more_data">Needs more data</option>
            </select>
          </div>

          {state === "overridden" ? (
            <div className="space-y-2">
              <label htmlFor="override-reason" className="text-sm font-medium">
                Override reason
              </label>
              <Textarea
                id="override-reason"
                value={overrideReason}
                onChange={(event) => setOverrideReason(event.target.value)}
                aria-describedby="override-reason-help"
              />
              <p id="override-reason-help" className="text-xs text-muted-foreground">
                Required when overriding the assessment judgment.
              </p>
            </div>
          ) : null}

          <div className="space-y-2">
            <label htmlFor="review-comment" className="text-sm font-medium">
              Comment
            </label>
            <Textarea
              id="review-comment"
              value={comment}
              onChange={(event) => setComment(event.target.value)}
              aria-describedby="review-comment-help"
            />
            <p id="review-comment-help" className="text-xs text-muted-foreground">
              {state === "needs_more_data"
                ? "Required when requesting more data."
                : "Optional for accepted reviews."}
            </p>
          </div>

          {validationError ? (
            <p role="alert" className="text-sm text-rose-700">
              {validationError}
            </p>
          ) : null}
        </div>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isSubmitting}
          >
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={isSubmitting}>
            {isSubmitting ? "Submitting…" : "Submit review"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
