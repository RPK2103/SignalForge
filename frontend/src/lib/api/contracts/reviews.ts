import type { HumanReviewState } from "./enums";

export type HumanReviewRequest = {
  state: HumanReviewState;
  reviewer_reference?: string | null;
  comment?: string | null;
  override_reason?: string | null;
};

export type { HumanReviewRecord } from "./assessments";
