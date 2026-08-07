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

/**
 * Known synthetic demo tenant ids from repository demo metadata
 * (Prompt 9 NovaBank seed constants). This is not organization-name matching
 * and must not be treated as a real-customer detector.
 */
export const KNOWN_SYNTHETIC_DEMO_TENANT_IDS = new Set(["novabank"]);

export function claimDisplayKind(claimType: string): ClaimDisplayKind {
  if (EVIDENCE_TYPES.has(claimType)) return "evidence";
  if (INFERENCE_TYPES.has(claimType)) return "inference";
  if (RECOMMENDATION_TYPES.has(claimType)) return "recommendation";
  if (LIMITATION_TYPES.has(claimType)) return "limitation";
  // Unknown claim types are limitations until explicitly classified.
  return "limitation";
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

/** True only for known synthetic demo tenant metadata (not org display names). */
export function isSyntheticDemoTenant(
  tenantId: string | null | undefined,
  organizationSlug?: string | null
): boolean {
  const id = (tenantId ?? "").toLowerCase();
  const slug = (organizationSlug ?? "").toLowerCase();
  return (
    KNOWN_SYNTHETIC_DEMO_TENANT_IDS.has(id) ||
    KNOWN_SYNTHETIC_DEMO_TENANT_IDS.has(slug)
  );
}

export const SYNTHETIC_DEMO_DISCLAIMER =
  "This tenant is a known fictional composite organization created solely for controlled product demonstration and testing. It is not affiliated with any real bank or company. All engineers, evidence and outcomes are synthetic and production-ineligible. Uncalibrated scores are not probabilities. Scenario results are decision-support only and are not causal claims.";

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
