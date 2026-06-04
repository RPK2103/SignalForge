export type ScoreTier = "green" | "amber" | "red";

export function getScoreTier(score: number): ScoreTier {
  if (score >= 90) return "green";
  if (score >= 70) return "amber";
  return "red";
}

export function scoreIndicatorClass(score: number): string {
  const tier = getScoreTier(score);
  if (tier === "green") return "bg-emerald-600";
  if (tier === "amber") return "bg-amber-500";
  return "bg-rose-500";
}

export function scoreBadgeClass(score: number): string {
  const tier = getScoreTier(score);
  if (tier === "green") return "bg-emerald-600 hover:bg-emerald-600";
  if (tier === "amber") return "bg-amber-500 hover:bg-amber-500";
  return "bg-rose-500 hover:bg-rose-500";
}

export function scoreValueClass(score: number): string {
  const tier = getScoreTier(score);
  if (tier === "green") return "text-emerald-700";
  if (tier === "amber") return "text-amber-700";
  return "text-rose-700";
}
