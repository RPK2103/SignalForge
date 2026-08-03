import { ObservabilityPanel } from "@/features/observability/observability-panel";

export const metadata = {
  title: "Observability · SignalForge",
};

export default function ObservabilityPage() {
  return (
    <div className="min-h-full bg-slate-50/80">
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold">Observability & AI quality</h1>
          <p className="text-sm text-muted-foreground">
            Operational reliability and AI trustworthiness signals for the
            selected tenant. Authenticated and role-aware.
          </p>
        </header>
        <ObservabilityPanel />
      </div>
    </div>
  );
}
