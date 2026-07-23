import { CircleCheck, CircleX } from "lucide-react";

type DeliveryReadinessBannerProps = {
  readinessScore: number | null;
  readinessStatus?: string | null;
  reason?: string | null;
};

export function DeliveryReadinessBanner({
  readinessScore,
  readinessStatus,
  reason,
}: DeliveryReadinessBannerProps) {
  if (readinessScore === null || !readinessStatus) {
    return null;
  }

  const isReady = readinessScore >= 70;

  return (
    <section
      aria-label="Delivery readiness"
      className={
        isReady
          ? "flex flex-col gap-3 rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
          : "flex flex-col gap-3 rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
      }
    >
      <div className="flex items-start gap-3 sm:items-center">
        <div
          className={
            isReady
              ? "flex size-9 shrink-0 items-center justify-center rounded-md bg-emerald-100 text-emerald-700"
              : "flex size-9 shrink-0 items-center justify-center rounded-md bg-amber-100 text-amber-700"
          }
        >
          {isReady ? (
            <CircleCheck className="size-5" aria-hidden />
          ) : (
            <CircleX className="size-5" aria-hidden />
          )}
        </div>
        <div>
          <p
            className={
              isReady
                ? "text-xs font-medium uppercase tracking-wide text-emerald-800/70"
                : "text-xs font-medium uppercase tracking-wide text-amber-800/70"
            }
          >
            Delivery Readiness (deterministic)
          </p>
          <p
            className={
              isReady
                ? "text-base font-semibold text-emerald-900"
                : "text-base font-semibold text-amber-900"
            }
          >
            {readinessStatus} · {readinessScore}/100
          </p>
        </div>
      </div>
      {reason ? (
        <p
          className={
            isReady
              ? "text-sm text-emerald-800/80 sm:max-w-md sm:text-right"
              : "text-sm text-amber-800/80 sm:max-w-md sm:text-right"
          }
        >
          {reason}
        </p>
      ) : null}
    </section>
  );
}
