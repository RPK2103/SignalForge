/**
 * Map Chief-of-Staff claim types to honest display labels.
 * Evidence / inference / recommendation — never employee ranking.
 */
export type ClaimDisplayKind =
  | "evidence"
  | "inference"
  | "recommendation"
  | "limitation";

const EVIDENCE_TYPES = new Set([
  "source_fact",
  "deterministic_finding",
  "deterministic_change",
]);

const INFERENCE_TYPES = new Set([
  "prediction_estimate",
  "scenario_implication",
]);

const RECOMMENDATION_TYPES = new Set(["advisory_option"]);

const LIMITATION_TYPES = new Set(["evidence_gap", "limitation"]);

export function claimDisplayKind(claimType: string): ClaimDisplayKind {
  if (EVIDENCE_TYPES.has(claimType)) return "evidence";
  if (INFERENCE_TYPES.has(claimType)) return "inference";
  if (RECOMMENDATION_TYPES.has(claimType)) return "recommendation";
  if (LIMITATION_TYPES.has(claimType)) return "limitation";
  return "inference";
}

export function claimKindLabel(kind: ClaimDisplayKind): string {
  switch (kind) {
    case "evidence":
      return "Evidence";
    case "inference":
      return "Inference";
    case "recommendation":
      return "Recommendation";
    case "limitation":
      return "Limitation";
  }
}

/** Known synthetic demo tenant ids/slugs — never treat as real customers. */
export function isSyntheticDemoTenant(
  tenantId: string | null | undefined,
  organizationSlug?: string | null
): boolean {
  const id = (tenantId ?? "").toLowerCase();
  const slug = (organizationSlug ?? "").toLowerCase();
  return id === "novabank" || slug === "novabank";
}

export const SYNTHETIC_DEMO_DISCLAIMER =
  "NovaBank is a fictional composite organization created solely for controlled product demonstration and testing. It is not affiliated with any real bank or company. All engineers, evidence and outcomes are synthetic and production-ineligible. Uncalibrated scores are not probabilities. Scenario results are decision-support only and are not causal claims.";

export function formatEstimateKind(kind: string | null | undefined): string {
  if (!kind) return "unavailable";
  if (kind === "uncalibrated_score") {
    return "uncalibrated score (not a probability)";
  }
  if (kind === "calibrated_probability") {
    return "calibrated probability (customer-validated models only)";
  }
  if (kind === "insufficient_data") {
    return "insufficient data";
  }
  return kind.replaceAll("_", " ");
}
