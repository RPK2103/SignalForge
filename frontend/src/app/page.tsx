import { AiExecutiveInsight } from "@/components/dashboard/ai-executive-insight";
import { DashboardHeader } from "@/components/dashboard/dashboard-header";
import { DeliveryReadinessBanner } from "@/components/dashboard/delivery-readiness-banner";
import { EngineerAnalysisCard } from "@/components/dashboard/engineer-analysis-card";
import { ExecutiveSummary } from "@/components/dashboard/executive-summary";
import { ProjectFitCard } from "@/components/dashboard/project-fit-card";
import { RiskAssessmentCard } from "@/components/dashboard/risk-assessment-card";
import { TeamRecommendationCard } from "@/components/dashboard/team-recommendation-card";

export default function Home() {
  return (
    <div className="min-h-full bg-slate-50/80">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-5 py-6 sm:px-6 sm:py-8">
        <DashboardHeader />
        <ExecutiveSummary />
        <DeliveryReadinessBanner />
        <AiExecutiveInsight />
        <section
          aria-label="Execution intelligence details"
          className="grid gap-4 md:grid-cols-2"
        >
          <EngineerAnalysisCard />
          <ProjectFitCard />
          <RiskAssessmentCard />
          <TeamRecommendationCard />
        </section>
        <footer className="border-t border-border/60 pt-4 text-center text-xs text-muted-foreground">
          SignalForge · Demo scenario · Azure AI Migration
        </footer>
      </div>
    </div>
  );
}
