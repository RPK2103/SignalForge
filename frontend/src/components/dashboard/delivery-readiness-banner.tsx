import { CircleCheck } from "lucide-react";

import { deliveryReadiness } from "@/lib/demo-data";

export function DeliveryReadinessBanner() {
  return (
    <section
      aria-label="Delivery readiness"
      className="flex flex-col gap-3 rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-start gap-3 sm:items-center">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-emerald-100 text-emerald-700">
          <CircleCheck className="size-5" />
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-emerald-800/70">
            {deliveryReadiness.title}
          </p>
          <p className="text-base font-semibold text-emerald-900">
            {deliveryReadiness.value}
          </p>
        </div>
      </div>
      <p className="text-sm text-emerald-800/80 sm:max-w-md sm:text-right">
        {deliveryReadiness.reason}
      </p>
    </section>
  );
}
