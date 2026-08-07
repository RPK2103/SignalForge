import { AppNav } from "@/components/layout/app-nav";
import { DashboardContainer } from "@/features/dashboard/dashboard-container";

export default function Home() {
  return (
    <div className="min-h-full bg-slate-50/80">
      <AppNav />
      <DashboardContainer />
    </div>
  );
}
