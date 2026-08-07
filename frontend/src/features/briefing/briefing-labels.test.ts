import { describe, expect, it } from "vitest";

import {
  SYNTHETIC_DEMO_DISCLAIMER,
  claimDisplayKind,
  claimKindLabel,
  formatEstimateKind,
  isSyntheticDemoTenant,
} from "./briefing-labels";

describe("briefing-labels", () => {
  it("maps claim types to evidence, inference, recommendation or limitation", () => {
    expect(claimDisplayKind("source_fact")).toBe("evidence");
    expect(claimDisplayKind("deterministic_finding")).toBe("evidence");
    expect(claimDisplayKind("prediction_estimate")).toBe("inference");
    expect(claimDisplayKind("scenario_implication")).toBe("inference");
    expect(claimDisplayKind("advisory_option")).toBe("recommendation");
    expect(claimDisplayKind("evidence_gap")).toBe("limitation");
    expect(claimKindLabel("evidence")).toBe("Evidence");
  });

  it("labels synthetic NovaBank tenants only", () => {
    expect(isSyntheticDemoTenant("novabank", "novabank")).toBe(true);
    expect(isSyntheticDemoTenant("acme", "acme")).toBe(false);
    expect(SYNTHETIC_DEMO_DISCLAIMER).toMatch(/fictional/i);
    expect(SYNTHETIC_DEMO_DISCLAIMER).toMatch(/not.*probabilities/i);
  });

  it("does not present uncalibrated scores as probabilities", () => {
    expect(formatEstimateKind("uncalibrated_score")).toMatch(/not a probability/i);
    expect(formatEstimateKind("insufficient_data")).toBe("insufficient data");
  });
});
