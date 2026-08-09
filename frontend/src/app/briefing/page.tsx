import { AppNav } from "@/components/layout/app-nav";
import { ExecutiveBriefingPanel } from "@/features/briefing/executive-briefing-panel";

export const metadata = {
  title: "Executive briefing · SignalForge",
  description:
    "Tenant-scoped delivery portfolio, findings, scenarios and Chief-of-Staff briefs.",
};

export default function BriefingPage() {
  return (
    <div className="min-h-full bg-slate-50/80">
      <AppNav />
      <div className="mx-auto max-w-6xl space-y-6 px-4 py-8">
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold">Executive briefing</h1>
          <p className="text-sm text-muted-foreground">
            Authenticated, tenant-scoped delivery intelligence. No mock
            fallback. Synthetic demo tenants are labelled explicitly.
          </p>
        </header>
        <ExecutiveBriefingPanel />
      </div>
    </div>
  );
}
