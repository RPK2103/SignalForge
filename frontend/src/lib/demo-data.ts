/** Test fixtures — not used in production runtime. */
export const demoScenario = {
  project: "Azure AI Migration",
  engineer: "Kavi",
} as const;

export const capabilityScores = [
  { label: "Execution", score: 90 },
  { label: "Backend", score: 85 },
  { label: "Cloud", score: 80 },
  { label: "AI Readiness", score: 88 },
] as const;

export const projectFit = {
  fitScore: 100,
  recommendation: "Strong Fit",
  matchedSkills: ["Azure", "Python", "Generative AI"],
} as const;

export const riskAssessment = {
  riskScore: 0,
  riskLevel: "Low",
  mitigationPlan: "Assign with light review from lead",
} as const;

export const executiveSummary = {
  kpis: [
    { label: "Fit Score", value: "100" },
    { label: "Delivery Risk", value: "Low" },
    { label: "Capability Coverage", value: "100%" },
    { label: "Execution Confidence", value: "96%" },
  ],
  insight:
    "Kavi is strongly aligned to Azure AI Migration. The recommended team provides full capability coverage with minimal delivery risk and high execution confidence.",
} as const;

export const deliveryReadiness = {
  title: "Delivery Readiness",
  value: "Ready for Execution",
  reason: "Required capabilities covered and delivery risk is low.",
} as const;

export const aiExecutiveInsight =
  "Kavi demonstrates strong capability alignment across Azure, Python, and Generative AI. Team composition provides balanced AI leadership, cloud expertise, and execution capacity. SignalForge predicts a high likelihood of successful project delivery.";

export const teamRecommendation = {
  members: [
    { name: "Kavi", role: "AI Engineer", score: 100 },
    { name: "Vikram", role: "Lead AI Engineer", score: 100 },
    { name: "Arjun", role: "Cloud Engineer", score: 67 },
  ],
  coverage: ["Azure", "Python", "Generative AI"],
  teamStatus: "Fully Staffed",
  coverageScore: 100,
} as const;
