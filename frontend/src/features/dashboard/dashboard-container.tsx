"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AiExecutiveInsight } from "@/components/dashboard/ai-executive-insight";
import { DashboardHeader } from "@/components/dashboard/dashboard-header";
import { DeliveryReadinessBanner } from "@/components/dashboard/delivery-readiness-banner";
import { EngineerAnalysisCard } from "@/components/dashboard/engineer-analysis-card";
import { ExecutiveSummary } from "@/components/dashboard/executive-summary";
import { ProjectFitCard } from "@/components/dashboard/project-fit-card";
import { RiskAssessmentCard } from "@/components/dashboard/risk-assessment-card";
import { TeamRecommendationCard } from "@/components/dashboard/team-recommendation-card";
import { ErrorState } from "@/components/ui/async-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AssessmentActions,
  CatalogSelector,
} from "@/features/assessment/catalog-selector";
import {
  DecisionTraceSection,
  SkillGapsSection,
} from "@/features/assessment/assessment-details";
import { AssessmentHistoryPanel } from "@/features/history/assessment-history-panel";
import { ReviewDialog } from "@/features/history/review-dialog";
import { LeadershipBriefPanel } from "@/features/leadership-brief/leadership-brief-panel";
import { SimulationPanel } from "@/features/simulation/simulation-panel";
import { useMountedRef } from "@/hooks/use-mounted";
import type {
  EngineerProfile,
  ProjectProfile,
  ReadinessAssessResponse,
  ReadinessPolicyMetadata,
} from "@/lib/api/contracts/catalog";
import type { AssessmentRecordResponse } from "@/lib/api/contracts/assessments";
import type { LeadershipBriefResponse } from "@/lib/api/contracts/leadership-briefs";
import type {
  SimulationHistoryItem,
  SimulationRecordResponse,
} from "@/lib/api/contracts/simulation-records";
import type { SimulationOperation, SimulationResponse } from "@/lib/api/contracts/simulations";
import {
  SignalForgeApiError,
  formatApiErrorMessage,
} from "@/lib/api/errors";
import { catalogService } from "@/lib/api/services/catalog-service";
import { assessmentService } from "@/lib/api/services/assessment-service";
import { leadershipBriefService } from "@/lib/api/services/leadership-brief-service";
import { readinessService } from "@/lib/api/services/readiness-service";
import { reviewService } from "@/lib/api/services/review-service";
import { simulationService } from "@/lib/api/services/simulation-service";
import { simulationRecordService } from "@/lib/api/services/simulation-record-service";
import {
  computeCapabilityCoveragePercent,
  formatConfidenceLabel,
  formatReadinessStatus,
  highestRiskSeverity,
} from "@/lib/display-formatters";

type ResultMode = "none" | "preview" | "persisted";

export function DashboardContainer() {
  const mountedRef = useMountedRef();
  const catalogAbortRef = useRef<AbortController | null>(null);
  const catalogRequestIdRef = useRef(0);
  const historyDetailRequestIdRef = useRef(0);
  const simulationDetailRequestIdRef = useRef(0);

  const [projects, setProjects] = useState<ProjectProfile[]>([]);
  const [engineers, setEngineers] = useState<EngineerProfile[]>([]);
  const [policy, setPolicy] = useState<ReadinessPolicyMetadata | null>(null);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [selectedEngineerIds, setSelectedEngineerIds] = useState<string[]>([]);

  const [resultMode, setResultMode] = useState<ResultMode>("none");
  const [previewResult, setPreviewResult] = useState<ReadinessAssessResponse | null>(null);
  const [persistedRecord, setPersistedRecord] = useState<AssessmentRecordResponse | null>(null);
  const [assessmentSubmitting, setAssessmentSubmitting] = useState(false);
  const [assessmentError, setAssessmentError] = useState<string | null>(null);

  const [historyList, setHistoryList] = useState<
    import("@/lib/api/contracts/assessments").AssessmentHistoryItem[]
  >([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyOffset, setHistoryOffset] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyDetail, setHistoryDetail] = useState<AssessmentRecordResponse | null>(null);
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false);
  const [historyDetailError, setHistoryDetailError] = useState<string | null>(null);

  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewSubmitting, setReviewSubmitting] = useState(false);

  const [simulationResult, setSimulationResult] = useState<SimulationResponse | null>(null);
  const [simulationRecord, setSimulationRecord] = useState<SimulationRecordResponse | null>(null);
  const [lastSimulationOperation, setLastSimulationOperation] =
    useState<SimulationOperation | null>(null);
  const [simulationRunning, setSimulationRunning] = useState(false);
  const [simulationPersisting, setSimulationPersisting] = useState(false);
  const [simulationError, setSimulationError] = useState<string | null>(null);
  const [simulationHistory, setSimulationHistory] = useState<SimulationHistoryItem[]>([]);
  const [simulationHistoryTotal, setSimulationHistoryTotal] = useState(0);
  const [simulationHistoryLoading, setSimulationHistoryLoading] = useState(false);
  const [selectedSimulationHistoryId, setSelectedSimulationHistoryId] = useState<string | null>(
    null
  );

  const [leadershipBriefs, setLeadershipBriefs] = useState<LeadershipBriefResponse[]>([]);
  const [selectedBriefId, setSelectedBriefId] = useState<string | null>(null);
  const [leadershipBriefLoading, setLeadershipBriefLoading] = useState(false);
  const [leadershipBriefGenerating, setLeadershipBriefGenerating] = useState(false);
  const [leadershipBriefError, setLeadershipBriefError] = useState<string | null>(null);

  const activeAssessment = useMemo(() => {
    if (resultMode === "persisted" && persistedRecord) {
      return persistedRecord.result;
    }
    if (resultMode === "preview" && previewResult) {
      return previewResult;
    }
    if (historyDetail) {
      return historyDetail.result;
    }
    return null;
  }, [historyDetail, persistedRecord, previewResult, resultMode]);

  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? null;
  const selectedEngineers = engineers.filter((engineer) =>
    selectedEngineerIds.includes(engineer.id)
  );

  const assessmentRecordId =
    persistedRecord?.assessment_record_id ?? historyDetail?.assessment_record_id ?? null;

  const selectedBrief =
    leadershipBriefs.find(
      (brief) => brief.leadership_brief_record_id === selectedBriefId
    ) ?? leadershipBriefs[0] ?? null;

  const loadCatalog = useCallback(async () => {
    catalogAbortRef.current?.abort();
    const controller = new AbortController();
    catalogAbortRef.current = controller;
    const requestId = ++catalogRequestIdRef.current;

    if (mountedRef.current) {
      setCatalogLoading(true);
      setCatalogError(null);
    }

    try {
      const [projectResponse, engineerResponse, policyResponse] = await Promise.all([
        catalogService.listProjects({ signal: controller.signal }),
        catalogService.listEngineers({ signal: controller.signal }),
        catalogService.listReadinessPolicies({ signal: controller.signal }),
      ]);

      if (!mountedRef.current || requestId !== catalogRequestIdRef.current) return;

      setProjects(projectResponse.projects);
      setEngineers(engineerResponse.engineers);
      setPolicy(policyResponse.policies[0] ?? null);
      setCatalogLoading(false);
    } catch (error) {
      if (!mountedRef.current || requestId !== catalogRequestIdRef.current) return;
      const apiError =
        error instanceof SignalForgeApiError
          ? error
          : new SignalForgeApiError({
              message: "Failed to load catalog",
              category: "unknown_error",
              cause: error,
            });
      setCatalogError(formatApiErrorMessage(apiError));
      setCatalogLoading(false);
    }
  }, [mountedRef]);

  const loadHistory = useCallback(
    async (offset = 0, append = false) => {
      if (!mountedRef.current) return;
      setHistoryLoading(true);
      setHistoryError(null);

      try {
        const response = await assessmentService.list({ limit: 20, offset });
        if (!mountedRef.current) return;
        setHistoryList((current) =>
          append ? [...current, ...response.items] : response.items
        );
        setHistoryTotal(response.total);
        setHistoryOffset(offset + response.items.length);
        setHistoryLoading(false);
      } catch (error) {
        if (!mountedRef.current) return;
        const apiError =
          error instanceof SignalForgeApiError
            ? error
            : new SignalForgeApiError({
                message: "Failed to load history",
                category: "unknown_error",
                cause: error,
              });
        setHistoryError(formatApiErrorMessage(apiError));
        setHistoryLoading(false);
      }
    },
    [mountedRef]
  );

  const loadSimulationHistory = useCallback(async () => {
    if (!mountedRef.current) return;
    setSimulationHistoryLoading(true);
    try {
      const response = await simulationRecordService.list({ limit: 20, offset: 0 });
      if (!mountedRef.current) return;
      setSimulationHistory(response.items);
      setSimulationHistoryTotal(response.total);
    } finally {
      if (mountedRef.current) setSimulationHistoryLoading(false);
    }
  }, [mountedRef]);

  const loadLeadershipBriefs = useCallback(
    async (recordId: string) => {
      if (!mountedRef.current) return;
      setLeadershipBriefLoading(true);
      setLeadershipBriefError(null);
      try {
        const briefs = await leadershipBriefService.list(recordId);
        if (!mountedRef.current) return;
        setLeadershipBriefs(briefs);
        setSelectedBriefId(briefs[0]?.leadership_brief_record_id ?? null);
      } catch (error) {
        if (!mountedRef.current) return;
        const apiError =
          error instanceof SignalForgeApiError
            ? error
            : new SignalForgeApiError({
                message: "Failed to load briefs",
                category: "unknown_error",
                cause: error,
              });
        setLeadershipBriefError(formatApiErrorMessage(apiError));
      } finally {
        if (mountedRef.current) setLeadershipBriefLoading(false);
      }
    },
    [mountedRef]
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadCatalog();
      void loadHistory();
      void loadSimulationHistory();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadCatalog, loadHistory, loadSimulationHistory]);

  useEffect(() => {
    if (!assessmentRecordId) {
      const timer = window.setTimeout(() => {
        setLeadershipBriefs([]);
        setSelectedBriefId(null);
      }, 0);
      return () => window.clearTimeout(timer);
    }

    const timer = window.setTimeout(() => {
      void loadLeadershipBriefs(assessmentRecordId);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [assessmentRecordId, loadLeadershipBriefs]);

  const handleProjectChange = (projectId: string) => {
    setSelectedProjectId(projectId);
    setPreviewResult(null);
    setPersistedRecord(null);
    setResultMode("none");
    setAssessmentError(null);
  };

  const handleEngineerToggle = (engineerId: string) => {
    setSelectedEngineerIds((current) => {
      if (current.includes(engineerId)) {
        return current.filter((id) => id !== engineerId);
      }
      return [...current, engineerId];
    });
    setPreviewResult(null);
    setPersistedRecord(null);
    setResultMode("none");
    setAssessmentError(null);
  };

  const canSubmit = Boolean(selectedProjectId && selectedEngineerIds.length > 0);

  const runAssessment = async (persist: boolean) => {
    if (!canSubmit || assessmentSubmitting) return;

    setAssessmentSubmitting(true);
    setAssessmentError(null);

    const payload = {
      project_id: selectedProjectId,
      engineer_ids: selectedEngineerIds,
      policy_version: policy?.version,
    };

    try {
      if (persist) {
        const record = await assessmentService.create(payload);
        if (!mountedRef.current) return;
        setPersistedRecord(record);
        setPreviewResult(null);
        setResultMode("persisted");
        setHistoryDetail(record);
        void loadHistory();
      } else {
        const result = await readinessService.assess(payload);
        if (!mountedRef.current) return;
        setPreviewResult(result);
        setPersistedRecord(null);
        setResultMode("preview");
      }
    } catch (error) {
      if (!mountedRef.current) return;
      const apiError =
        error instanceof SignalForgeApiError
          ? error
          : new SignalForgeApiError({
              message: "Assessment failed",
              category: "unknown_error",
              cause: error,
            });
      setAssessmentError(formatApiErrorMessage(apiError));
    } finally {
      if (mountedRef.current) setAssessmentSubmitting(false);
    }
  };

  const openHistoryDetail = async (recordId: string) => {
    const requestId = ++historyDetailRequestIdRef.current;
    setHistoryDetailLoading(true);
    setHistoryDetailError(null);

    try {
      const detail = await assessmentService.getById(recordId);
      if (
        !mountedRef.current ||
        requestId !== historyDetailRequestIdRef.current
      ) {
        return;
      }
      setHistoryDetail(detail);
      setHistoryDetailLoading(false);
    } catch (error) {
      if (
        !mountedRef.current ||
        requestId !== historyDetailRequestIdRef.current
      ) {
        return;
      }
      const apiError =
        error instanceof SignalForgeApiError
          ? error
          : new SignalForgeApiError({
              message: "Failed to load detail",
              category: "unknown_error",
              cause: error,
            });
      setHistoryDetailError(formatApiErrorMessage(apiError));
      setHistoryDetailLoading(false);
    }
  };

  const submitReview = async (payload: {
    state: import("@/lib/api/contracts/enums").HumanReviewState;
    comment?: string;
    override_reason?: string;
  }) => {
    if (!historyDetail) return;
    setReviewSubmitting(true);
    try {
      const updated = await reviewService.submit(
        historyDetail.assessment_record_id,
        payload
      );
      if (!mountedRef.current) return;
      setHistoryDetail(updated);
      if (persistedRecord?.assessment_record_id === updated.assessment_record_id) {
        setPersistedRecord(updated);
      }
      setReviewOpen(false);
      void loadHistory();
    } finally {
      if (mountedRef.current) setReviewSubmitting(false);
    }
  };

  const runSimulation = async (operation: SimulationOperation) => {
    if (!selectedProjectId || baselineEngineerIds.length === 0) return;
    setSimulationRunning(true);
    setSimulationError(null);
    setSimulationRecord(null);
    setLastSimulationOperation(operation);

    try {
      const result = await simulationService.run({
        project_id: selectedProjectId,
        baseline_engineer_ids: baselineEngineerIds,
        operation,
        policy_version: policy?.version,
      });
      if (!mountedRef.current) return;
      setSimulationResult(result);
    } catch (error) {
      if (!mountedRef.current) return;
      const apiError =
        error instanceof SignalForgeApiError
          ? error
          : new SignalForgeApiError({
              message: "Simulation failed",
              category: "unknown_error",
              cause: error,
            });
      setSimulationError(formatApiErrorMessage(apiError));
    } finally {
      if (mountedRef.current) setSimulationRunning(false);
    }
  };

  const persistSimulation = async () => {
    if (!simulationResult || !lastSimulationOperation || simulationPersisting) return;
    setSimulationPersisting(true);
    try {
      const record = await simulationRecordService.create({
        project_id: selectedProjectId,
        baseline_engineer_ids: baselineEngineerIds,
        operation: lastSimulationOperation,
        policy_version: policy?.version,
      });
      if (!mountedRef.current) return;
      setSimulationRecord(record);
      void loadSimulationHistory();
    } catch (error) {
      if (!mountedRef.current) return;
      const apiError =
        error instanceof SignalForgeApiError
          ? error
          : new SignalForgeApiError({
              message: "Failed to save simulation",
              category: "unknown_error",
              cause: error,
            });
      setSimulationError(formatApiErrorMessage(apiError));
    } finally {
      if (mountedRef.current) setSimulationPersisting(false);
    }
  };

  const generateLeadershipBrief = async () => {
    if (!assessmentRecordId || leadershipBriefGenerating) return;
    setLeadershipBriefGenerating(true);
    setLeadershipBriefError(null);
    try {
      await leadershipBriefService.generate(assessmentRecordId);
      if (!mountedRef.current) return;
      await loadLeadershipBriefs(assessmentRecordId);
    } catch (error) {
      if (!mountedRef.current) return;
      const apiError =
        error instanceof SignalForgeApiError
          ? error
          : new SignalForgeApiError({
              message: "Brief generation failed",
              category: "unknown_error",
              cause: error,
            });
      setLeadershipBriefError(formatApiErrorMessage(apiError));
    } finally {
      if (mountedRef.current) setLeadershipBriefGenerating(false);
    }
  };

  const baselineEngineerIds =
    activeAssessment?.team.map((member) => member.id) ?? selectedEngineerIds;

  const coveredCapabilities =
    activeAssessment?.coverage_results
      .filter((item) => item.level !== "missing")
      .map((item) => item.capability_name) ?? [];

  const kpis = activeAssessment
    ? [
        {
          label: "Readiness Score",
          value: String(activeAssessment.readiness_score),
        },
        {
          label: "Delivery Risk",
          value: highestRiskSeverity(activeAssessment),
        },
        {
          label: "Capability Coverage (derived)",
          value: `${computeCapabilityCoveragePercent(activeAssessment)}% covered`,
        },
        {
          label: "Execution Confidence",
          value: `${activeAssessment.confidence_score}% (${formatConfidenceLabel(activeAssessment.confidence_level)})`,
        },
      ]
    : [];

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-5 py-6 sm:px-6 sm:py-8">
      <DashboardHeader
        projectName={selectedProject?.name ?? activeAssessment?.project_name}
        engineerNames={
          activeAssessment?.team.map((member) => member.name) ??
          selectedEngineers.map((member) => member.name)
        }
        policyVersion={activeAssessment?.policy_version ?? policy?.version}
        isLive
      />

      <CatalogSelector
        projects={projects}
        engineers={engineers}
        policy={policy}
        selectedProjectId={selectedProjectId}
        selectedEngineerIds={selectedEngineerIds}
        onProjectChange={handleProjectChange}
        onEngineerToggle={handleEngineerToggle}
        isLoading={catalogLoading}
        errorMessage={catalogError}
        onRetry={() => void loadCatalog()}
      />

      <AssessmentActions
        onPreview={() => void runAssessment(false)}
        onPersist={() => void runAssessment(true)}
        isSubmitting={assessmentSubmitting}
        canSubmit={canSubmit}
      />

      {assessmentError ? (
        <ErrorState title="Assessment failed" message={assessmentError} />
      ) : null}

      {resultMode === "preview" ? (
        <p className="text-xs text-muted-foreground">
          Preview mode — results are compute-only and not saved to history.
        </p>
      ) : null}
      {resultMode === "persisted" && persistedRecord ? (
        <p className="text-xs text-muted-foreground">
          Persisted assessment · record {persistedRecord.assessment_record_id}
        </p>
      ) : null}

      <ExecutiveSummary
        kpis={kpis}
        insight={activeAssessment?.summary}
        sourceLabel={
          resultMode === "preview"
            ? "Compute-only preview"
            : "Deterministic assessment"
        }
      />

      <DeliveryReadinessBanner
        readinessScore={activeAssessment?.readiness_score ?? null}
        readinessStatus={
          activeAssessment
            ? formatReadinessStatus(activeAssessment.readiness_score)
            : null
        }
        reason={activeAssessment?.summary}
      />

      <AiExecutiveInsight
        brief={selectedBrief}
        isGenerating={leadershipBriefGenerating}
        canGenerate={Boolean(assessmentRecordId)}
        onGenerate={() => void generateLeadershipBrief()}
        assessmentRecordId={assessmentRecordId}
      />

      {leadershipBriefError ? (
        <ErrorState title="Leadership Brief error" message={leadershipBriefError} />
      ) : null}

      <section
        aria-label="Execution intelligence details"
        className="grid gap-4 md:grid-cols-2"
      >
        <EngineerAnalysisCard
          engineerName={selectedEngineers[0]?.name}
          dimensionScores={activeAssessment?.dimension_scores}
        />
        <ProjectFitCard
          projectName={activeAssessment?.project_name ?? selectedProject?.name}
          readinessScore={activeAssessment?.readiness_score ?? null}
          coverageResults={activeAssessment?.coverage_results}
        />
        <RiskAssessmentCard
          projectName={activeAssessment?.project_name ?? selectedProject?.name}
          riskFindings={activeAssessment?.risk_findings}
          mitigations={simulationResult?.recommended_mitigations.map((item) => ({
            title: item.title,
            action: item.action,
          }))}
        />
        <TeamRecommendationCard
          projectName={activeAssessment?.project_name ?? selectedProject?.name}
          team={activeAssessment?.team ?? selectedEngineers}
          coverageScore={
            activeAssessment
              ? computeCapabilityCoveragePercent(activeAssessment)
              : null
          }
          coveredCapabilities={coveredCapabilities}
        />
      </section>

      {activeAssessment ? (
        <>
          <SkillGapsSection gaps={activeAssessment.skill_gaps} />
          <DecisionTraceSection entries={activeAssessment.decision_trace} />
        </>
      ) : null}

      <Tabs defaultValue="history">
        <TabsList>
          <TabsTrigger value="history">History & Reviews</TabsTrigger>
          <TabsTrigger value="simulation">Simulation</TabsTrigger>
          <TabsTrigger value="briefs">Leadership Briefs</TabsTrigger>
        </TabsList>
        <TabsContent value="history" className="mt-4">
          <AssessmentHistoryPanel
            items={historyList}
            total={historyTotal}
            selectedRecord={historyDetail}
            isLoading={historyLoading}
            isDetailLoading={historyDetailLoading}
            errorMessage={historyError}
            detailErrorMessage={historyDetailError}
            onRetry={() => void loadHistory()}
            onSelect={(recordId) => void openHistoryDetail(recordId)}
            onLoadMore={() => void loadHistory(historyOffset, true)}
            hasMore={historyList.length < historyTotal}
            onOpenReview={() => setReviewOpen(true)}
            isPersistedView
          />
        </TabsContent>
        <TabsContent value="simulation" className="mt-4">
          <SimulationPanel
            engineers={engineers}
            baselineEngineerIds={baselineEngineerIds}
            simulationResult={simulationResult}
            simulationRecord={simulationRecord}
            historyItems={simulationHistory}
            historyTotal={simulationHistoryTotal}
            isRunning={simulationRunning}
            isPersisting={simulationPersisting}
            isHistoryLoading={simulationHistoryLoading}
            errorMessage={simulationError ?? undefined}
            onRun={(operation) => void runSimulation(operation)}
            onPersist={() => void persistSimulation()}
            onSelectHistory={async (recordId) => {
              const requestId = ++simulationDetailRequestIdRef.current;
              setSelectedSimulationHistoryId(recordId);
              try {
                const detail = await simulationRecordService.getById(recordId);
                if (
                  !mountedRef.current ||
                  requestId !== simulationDetailRequestIdRef.current
                ) {
                  return;
                }
                setSimulationRecord(detail);
                setSimulationResult(null);
              } catch {
                /* detail errors surfaced via simulation panel if needed */
              }
            }}
            selectedHistoryId={selectedSimulationHistoryId}
            onRetryHistory={() => void loadSimulationHistory()}
          />
        </TabsContent>
        <TabsContent value="briefs" className="mt-4">
          {!assessmentRecordId ? (
            <p className="text-sm text-muted-foreground">
              Save or open a persisted assessment to view Leadership Brief history.
            </p>
          ) : (
            <LeadershipBriefPanel
              briefs={leadershipBriefs}
              selectedBrief={selectedBrief}
              isLoading={leadershipBriefLoading}
              errorMessage={leadershipBriefError ?? undefined}
              onSelect={setSelectedBriefId}
              onRetry={() =>
                assessmentRecordId
                  ? void loadLeadershipBriefs(assessmentRecordId)
                  : undefined
              }
            />
          )}
        </TabsContent>
      </Tabs>

      <ReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        onSubmit={submitReview}
        isSubmitting={reviewSubmitting}
      />

      <footer className="border-t border-border/60 pt-4 text-center text-xs text-muted-foreground">
        SignalForge · Live API integration · v2 endpoints
      </footer>
    </div>
  );
}
