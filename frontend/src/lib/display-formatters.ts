import type { ReadinessAssessResponse } from "@/lib/api/contracts/catalog";
import type { ConfidenceLevel } from "@/lib/api/contracts/enums";

export function formatReadinessStatus(score: number): string {
  if (score >= 85) return "Ready for Execution";
  if (score >= 70) return "Proceed with Conditions";
  if (score >= 50) return "Needs Strengthening";
  return "Not Ready";
}

export function formatConfidenceLabel(level: string): string {
  switch (level as ConfidenceLevel) {
    case "high":
      return "High";
    case "medium":
      return "Medium";
    case "low":
      return "Low";
    default:
      return level;
  }
}

export function formatPercent(value: number): string {
  return `${value}%`;
}

export function formatDelta(value: number): string {
  if (value > 0) return `+${value}`;
  if (value < 0) return String(value);
  return "0 (no change)";
}

export function deltaDirection(value: number): "positive" | "negative" | "neutral" {
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

export function computeCapabilityCoveragePercent(
  assessment: ReadinessAssessResponse
): number {
  const total = assessment.coverage_results.length;
  if (total === 0) return 0;
  const covered = assessment.coverage_results.filter(
    (item) => item.level !== "missing"
  ).length;
  return Math.round((covered / total) * 100);
}

export function highestRiskSeverity(
  assessment: ReadinessAssessResponse
): string {
  if (assessment.risk_findings.length === 0) return "Low";
  const order = { low: 0, medium: 1, high: 2 } as const;
  const max = assessment.risk_findings.reduce((current, finding) => {
    const severity = finding.severity as keyof typeof order;
    return order[severity] > order[current] ? severity : current;
  }, "low" as keyof typeof order);
  return max.charAt(0).toUpperCase() + max.slice(1);
}

export function formatDateTime(value: string): string {
  try {
    return new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export function dimensionLabel(dimension: string): string {
  return dimension
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
