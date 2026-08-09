"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/async-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAsyncRequest } from "@/hooks/use-async-request";
import type {
  ChiefOfStaffBriefRecord,
  ChiefOfStaffCitation,
  ChiefOfStaffClaim,
} from "@/lib/api/contracts/chief-of-staff";
import type {
  GraphFinding,
  GraphSummary,
  Initiative,
  Organization,
} from "@/lib/api/contracts/enterprise";
import type {
  ScenarioDefinition,
  ScenarioResult,
  ScenarioRun,
} from "@/lib/api/contracts/scenarios";
import { chiefOfStaffService } from "@/lib/api/services/chief-of-staff-service";
import { enterpriseService } from "@/lib/api/services/enterprise-service";
import { scenarioService } from "@/lib/api/services/scenario-service";
import {
  SYNTHETIC_DEMO_DISCLAIMER,
  claimDisplayKind,
  claimKindLabel,
  formatEstimateKind,
  isSyntheticDemoTenant,
} from "./briefing-labels";

const PAGE_SIZE = 10;

type OverviewData = {
  organization: Organization;
  initiatives: { items: Initiative[]; total: number };
  graphSummary: GraphSummary | null;
  findings: { items: GraphFinding[]; total: number };
  scenarios: { items: ScenarioDefinition[]; total: number };
  briefs: { items: ChiefOfStaffBriefRecord[]; total: number };
  graphForbidden: boolean;
  scenariosForbidden: boolean;
  briefsForbidden: boolean;
};

type ScenarioDetail = {
  runs: ScenarioRun[];
  result: ScenarioResult | null;
  resultError: string | null;
};

type BriefDetail = {
  brief: ChiefOfStaffBriefRecord;
  claims: ChiefOfStaffClaim[];
  citations: ChiefOfStaffCitation[];
};

function statusCodeOf(error: unknown): number | undefined {
  if (error && typeof error === "object" && "statusCode" in error) {
    return Number((error as { statusCode?: number }).statusCode);
  }
  return undefined;
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-muted/10 px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function claimBadgeVariant(
  kind: ReturnType<typeof claimDisplayKind>
): "default" | "secondary" | "outline" | "destructive" {
  if (kind === "evidence") return "default";
  if (kind === "recommendation") return "secondary";
  if (kind === "limitation") return "outline";
  return "outline";
}

function nodeCount(
  summary: GraphSummary | null,
  nodeType: string
): string {
  if (!summary) return "—";
  const value = summary.nodes_by_type[nodeType];
  return value === undefined ? "—" : String(value);
}

export function ExecutiveBriefingPanel() {
  const { state, execute, setState } = useAsyncRequest<OverviewData>();
  const [initiativeOffset, setInitiativeOffset] = useState(0);
  const [findingOffset, setFindingOffset] = useState(0);
  const [scenarioOffset, setScenarioOffset] = useState(0);
  const [briefOffset, setBriefOffset] = useState(0);
  const [sectionPaging, setSectionPaging] = useState<string | null>(null);

  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(
    null
  );
  const [selectedBriefId, setSelectedBriefId] = useState<string | null>(null);
  const [scenarioDetail, setScenarioDetail] = useState<ScenarioDetail | null>(
    null
  );
  const [briefDetail, setBriefDetail] = useState<BriefDetail | null>(null);
  const [scenarioDetailError, setScenarioDetailError] = useState<string | null>(
    null
  );
  const [briefDetailError, setBriefDetailError] = useState<string | null>(null);
  const [scenarioDetailLoading, setScenarioDetailLoading] = useState(false);
  const [briefDetailLoading, setBriefDetailLoading] = useState(false);

  const loadOverview = useCallback(() => {
    void execute(async (signal) => {
      const organization = await enterpriseService.getOrganization({ signal });
      const initiatives = await enterpriseService.listInitiatives(
        { limit: PAGE_SIZE, offset: 0 },
        { signal }
      );

      let graphSummary: GraphSummary | null = null;
      let findings: OverviewData["findings"] = { items: [], total: 0 };
      let graphForbidden = false;
      try {
        graphSummary = await enterpriseService.getGraphSummary({ signal });
        findings = await enterpriseService.listFindings(
          { limit: PAGE_SIZE, offset: 0 },
          { signal }
        );
      } catch (error) {
        if (statusCodeOf(error) === 403) {
          graphForbidden = true;
        } else {
          throw error;
        }
      }

      let scenarios: OverviewData["scenarios"] = { items: [], total: 0 };
      let scenariosForbidden = false;
      try {
        scenarios = await scenarioService.listScenarios(
          { limit: PAGE_SIZE, offset: 0 },
          { signal }
        );
      } catch (error) {
        if (statusCodeOf(error) === 403) {
          scenariosForbidden = true;
        } else {
          throw error;
        }
      }

      let briefs: OverviewData["briefs"] = { items: [], total: 0 };
      let briefsForbidden = false;
      try {
        briefs = await chiefOfStaffService.listBriefs(
          { limit: PAGE_SIZE, offset: 0 },
          { signal }
        );
      } catch (error) {
        if (statusCodeOf(error) === 403) {
          briefsForbidden = true;
        } else {
          throw error;
        }
      }

      return {
        organization,
        initiatives: { items: initiatives.items, total: initiatives.total },
        graphSummary,
        findings: { items: findings.items, total: findings.total },
        scenarios: { items: scenarios.items, total: scenarios.total },
        briefs: { items: briefs.items, total: briefs.total },
        graphForbidden,
        scenariosForbidden,
        briefsForbidden,
      };
    });
  }, [execute]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  // Bounded section pagination — refetch only the paged resource.
  // Skip the first effect pass: overview already loaded offset 0.
  const skipInitiativePage = useRef(true);
  const skipFindingPage = useRef(true);
  const skipScenarioPage = useRef(true);
  const skipBriefPage = useRef(true);

  useEffect(() => {
    if (skipInitiativePage.current) {
      skipInitiativePage.current = false;
      return;
    }
    let cancelled = false;
    setSectionPaging("initiatives");
    void (async () => {
      try {
        const page = await enterpriseService.listInitiatives({
          limit: PAGE_SIZE,
          offset: initiativeOffset,
        });
        if (cancelled) return;
        setState((prev) =>
          prev.data
            ? {
                ...prev,
                data: {
                  ...prev.data,
                  initiatives: { items: page.items, total: page.total },
                },
              }
            : prev
        );
      } catch {
        // Keep prior page visible.
      } finally {
        if (!cancelled) setSectionPaging(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [initiativeOffset, setState]);

  useEffect(() => {
    if (skipFindingPage.current) {
      skipFindingPage.current = false;
      return;
    }
    let cancelled = false;
    setSectionPaging("findings");
    void (async () => {
      try {
        const page = await enterpriseService.listFindings({
          limit: PAGE_SIZE,
          offset: findingOffset,
        });
        if (cancelled) return;
        setState((prev) =>
          prev.data
            ? {
                ...prev,
                data: {
                  ...prev.data,
                  findings: { items: page.items, total: page.total },
                },
              }
            : prev
        );
      } catch {
        // Keep prior findings visible.
      } finally {
        if (!cancelled) setSectionPaging(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [findingOffset, setState]);

  useEffect(() => {
    if (skipScenarioPage.current) {
      skipScenarioPage.current = false;
      return;
    }
    let cancelled = false;
    setSectionPaging("scenarios");
    void (async () => {
      try {
        const page = await scenarioService.listScenarios({
          limit: PAGE_SIZE,
          offset: scenarioOffset,
        });
        if (cancelled) return;
        setState((prev) =>
          prev.data
            ? {
                ...prev,
                data: {
                  ...prev.data,
                  scenarios: { items: page.items, total: page.total },
                },
              }
            : prev
        );
      } catch {
        // Keep prior scenarios visible.
      } finally {
        if (!cancelled) setSectionPaging(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [scenarioOffset, setState]);

  useEffect(() => {
    if (skipBriefPage.current) {
      skipBriefPage.current = false;
      return;
    }
    let cancelled = false;
    setSectionPaging("briefs");
    void (async () => {
      try {
        const page = await chiefOfStaffService.listBriefs({
          limit: PAGE_SIZE,
          offset: briefOffset,
        });
        if (cancelled) return;
        setState((prev) =>
          prev.data
            ? {
                ...prev,
                data: {
                  ...prev.data,
                  briefs: { items: page.items, total: page.total },
                },
              }
            : prev
        );
      } catch {
        // Keep prior briefs visible.
      } finally {
        if (!cancelled) setSectionPaging(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [briefOffset, setState]);

  useEffect(() => {
    if (!selectedScenarioId) {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const runsPage = await scenarioService.listRuns(selectedScenarioId, {
          limit: 5,
          offset: 0,
        });
        const latest = runsPage.items[0] ?? null;
        let result: ScenarioResult | null = null;
        let resultError: string | null = null;
        if (latest) {
          try {
            result = await scenarioService.getRunResult(latest.scenario_run_id);
          } catch (error) {
            const status = statusCodeOf(error);
            if (status === 404) {
              result = null;
              resultError = null;
            } else {
              resultError =
                error instanceof Error
                  ? error.message
                  : "Could not load scenario run result";
            }
          }
        }
        if (!cancelled) {
          setScenarioDetail({ runs: runsPage.items, result, resultError });
          setScenarioDetailError(null);
          setScenarioDetailLoading(false);
        }
      } catch (error) {
        if (!cancelled) {
          setScenarioDetailError(
            error instanceof Error
              ? error.message
              : "Could not load scenario detail"
          );
          setScenarioDetail(null);
          setScenarioDetailLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedScenarioId]);

  useEffect(() => {
    if (!selectedBriefId) {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const [brief, claims, citations] = await Promise.all([
          chiefOfStaffService.getBrief(selectedBriefId),
          chiefOfStaffService.listClaims(selectedBriefId),
          chiefOfStaffService.listCitations(selectedBriefId),
        ]);
        if (!cancelled) {
          setBriefDetail({ brief, claims, citations });
          setBriefDetailError(null);
          setBriefDetailLoading(false);
        }
      } catch (error) {
        if (!cancelled) {
          setBriefDetailError(
            error instanceof Error
              ? error.message
              : "Could not load Chief-of-Staff brief"
          );
          setBriefDetail(null);
          setBriefDetailLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedBriefId]);

  // Full-page loading only on first load (no prior data).
  if (
    (state.status === "loading" || state.status === "idle") &&
    !state.data
  ) {
    return (
      <LoadingState
        title="Loading executive briefing"
        message="Fetching tenant portfolio, findings, scenarios and briefs…"
      />
    );
  }

  if (state.status === "error" && !state.data) {
    const unauthorized = state.error?.statusCode === 401;
    const forbidden = state.error?.statusCode === 403;
    return (
      <ErrorState
        title={
          unauthorized
            ? "Authentication required"
            : forbidden
              ? "You do not have access to this briefing"
              : "Could not load executive briefing"
        }
        message={
          unauthorized
            ? "Provide a valid bearer token for this environment. There is no anonymous demo path."
            : forbidden
              ? "This area requires enterprise.read (and related read permissions for graph, scenarios and Chief of Staff)."
              : (state.errorMessage ?? "An unexpected error occurred.")
        }
        onRetry={unauthorized || forbidden ? undefined : loadOverview}
      />
    );
  }

  const data = state.data;
  if (!data) {
    return (
      <EmptyState
        title="No briefing data"
        message="Authenticated APIs returned no tenant portfolio content."
      />
    );
  }

  const visibleScenarioDetail = selectedScenarioId ? scenarioDetail : null;
  const visibleBriefDetail = selectedBriefId ? briefDetail : null;

  const synthetic = isSyntheticDemoTenant(
    data.organization.tenant_id,
    data.organization.slug
  );

  return (
    <div className="space-y-6" data-testid="executive-briefing-panel">
      {synthetic ? (
        <div
          role="note"
          data-testid="synthetic-demo-banner"
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
        >
          <p className="font-medium">Synthetic demo data</p>
          <p className="mt-1 text-amber-900/90">{SYNTHETIC_DEMO_DISCLAIMER}</p>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="font-heading text-base leading-snug font-medium">
              {data.organization.name}
            </h2>
          </CardTitle>
          <CardDescription>
            Tenant-scoped delivery portfolio overview. Counts come from
            initiative list totals and Delivery Graph node types when available
            — not from demo-only aggregate endpoints. SignalForge evaluates
            delivery-system risk, capability coverage, dependencies and evidence.
            It is not intended to rank individual employees or automate
            employment decisions.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricTile
            label="Initiatives"
            value={String(data.initiatives.total)}
          />
          <MetricTile
            label="Projects (graph)"
            value={nodeCount(data.graphSummary, "project")}
          />
          <MetricTile
            label="Engineers (graph)"
            value={nodeCount(data.graphSummary, "engineer")}
          />
          <MetricTile
            label="Repositories (graph)"
            value={nodeCount(data.graphSummary, "repository")}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="font-heading text-base leading-snug font-medium">
              Delivery Graph
            </h2>
          </CardTitle>
          <CardDescription>
            Rule-based graph confidence is not a delivery probability.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {data.graphForbidden ? (
            <ErrorState
              title="Graph access denied"
              message="Requires graph.read permission."
            />
          ) : data.graphSummary ? (
            <div className="grid gap-3 sm:grid-cols-3">
              <MetricTile
                label="Nodes"
                value={String(data.graphSummary.node_count)}
              />
              <MetricTile
                label="Edges"
                value={String(data.graphSummary.edge_count)}
              />
              <MetricTile
                label="Active findings"
                value={String(data.graphSummary.active_finding_count)}
              />
            </div>
          ) : (
            <EmptyState
              title="No delivery graph yet"
              message="Run graph materialization for this tenant, then retry."
            />
          )}

          {sectionPaging === "findings" ? (
            <p className="text-xs text-muted-foreground">Updating findings…</p>
          ) : null}

          {data.findings.items.length === 0 ? (
            !data.graphForbidden ? (
              <EmptyState
                title="No active findings"
                message="Findings appear after graph analysis for the selected tenant."
              />
            ) : null
          ) : (
            <ul className="space-y-2" aria-label="Graph findings">
              {data.findings.items.map((finding) => (
                <li
                  key={finding.graph_finding_id}
                  className="rounded-md border border-border/70 px-3 py-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{finding.title}</p>
                    <Badge variant="outline">{finding.severity}</Badge>
                    <Badge variant="secondary">{finding.finding_type}</Badge>
                  </div>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {finding.explanation}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {data.findings.total > PAGE_SIZE ? (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={findingOffset === 0 || sectionPaging === "findings"}
                onClick={() =>
                  setFindingOffset((value) => Math.max(0, value - PAGE_SIZE))
                }
              >
                Previous findings
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  findingOffset + PAGE_SIZE >= data.findings.total ||
                  sectionPaging === "findings"
                }
                onClick={() => setFindingOffset((value) => value + PAGE_SIZE)}
              >
                Next findings
              </Button>
              <span className="text-xs text-muted-foreground">
                {findingOffset + 1}–
                {Math.min(findingOffset + PAGE_SIZE, data.findings.total)} of{" "}
                {data.findings.total}
              </span>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="font-heading text-base leading-snug font-medium">
              Initiatives
            </h2>
          </CardTitle>
          <CardDescription>
            Select initiatives by name. Identifiers are discovered from the API
            — nothing is hardcoded.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {sectionPaging === "initiatives" ? (
            <p className="text-xs text-muted-foreground">
              Updating initiatives…
            </p>
          ) : null}
          {data.initiatives.items.length === 0 ? (
            <EmptyState
              title="No initiatives"
              message="Seed or ingest initiatives for this tenant."
            />
          ) : (
            <ul className="space-y-2" aria-label="Initiatives">
              {data.initiatives.items.map((initiative) => (
                <li
                  key={initiative.initiative_id}
                  className="rounded-md border border-border/70 px-3 py-2"
                  data-testid="initiative-row"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{initiative.name}</p>
                    <Badge variant="outline">{initiative.status}</Badge>
                    <Badge variant="secondary">{initiative.criticality}</Badge>
                  </div>
                  {initiative.description ? (
                    <p className="mt-1 text-sm text-muted-foreground">
                      {initiative.description}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          {data.initiatives.total > PAGE_SIZE ? (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  initiativeOffset === 0 || sectionPaging === "initiatives"
                }
                onClick={() =>
                  setInitiativeOffset((value) => Math.max(0, value - PAGE_SIZE))
                }
              >
                Previous initiatives
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  initiativeOffset + PAGE_SIZE >= data.initiatives.total ||
                  sectionPaging === "initiatives"
                }
                onClick={() =>
                  setInitiativeOffset((value) => value + PAGE_SIZE)
                }
              >
                Next initiatives
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="font-heading text-base leading-snug font-medium">
              Counterfactual scenarios
            </h2>
          </CardTitle>
          <CardDescription>
            Scenario outputs are decision-support overlays — not causal
            predictions.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {data.scenariosForbidden ? (
            <ErrorState
              title="Scenario access denied"
              message="Requires scenarios.read permission."
            />
          ) : data.scenarios.items.length === 0 ? (
            <EmptyState
              title="No scenarios"
              message="Seed scenario definitions and materialize runs for this tenant."
            />
          ) : (
            <ul className="space-y-2" aria-label="Scenarios">
              {data.scenarios.items.map((scenario) => {
                const selected =
                  selectedScenarioId === scenario.scenario_definition_id;
                return (
                  <li key={scenario.scenario_definition_id}>
                    <button
                      type="button"
                      data-testid="scenario-select"
                      aria-pressed={selected}
                      className="w-full rounded-md border border-border/70 px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => {
                        setScenarioDetailLoading(true);
                        setScenarioDetailError(null);
                        setScenarioDetail(null);
                        setSelectedScenarioId(scenario.scenario_definition_id);
                      }}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">
                          {scenario.name}
                        </span>
                        <Badge variant="outline">{scenario.scenario_kind}</Badge>
                      </div>
                      {scenario.description ? (
                        <p className="mt-1 text-sm text-muted-foreground">
                          {scenario.description}
                        </p>
                      ) : null}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {data.scenarios.total > PAGE_SIZE ? (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  scenarioOffset === 0 || sectionPaging === "scenarios"
                }
                onClick={() =>
                  setScenarioOffset((value) => Math.max(0, value - PAGE_SIZE))
                }
              >
                Previous scenarios
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  scenarioOffset + PAGE_SIZE >= data.scenarios.total ||
                  sectionPaging === "scenarios"
                }
                onClick={() => setScenarioOffset((value) => value + PAGE_SIZE)}
              >
                Next scenarios
              </Button>
            </div>
          ) : null}

          {scenarioDetailError ? (
            <ErrorState
              title="Scenario detail failed"
              message={scenarioDetailError}
            />
          ) : null}

          {selectedScenarioId &&
          scenarioDetailLoading &&
          !visibleScenarioDetail ? (
            <LoadingState title="Loading scenario result" />
          ) : null}
          {visibleScenarioDetail ? (
            <div
              className="space-y-2 rounded-md border border-border/70 bg-muted/10 px-3 py-3"
              data-testid="scenario-detail"
            >
              {visibleScenarioDetail.resultError ? (
                <ErrorState
                  title="Scenario result unavailable"
                  message={visibleScenarioDetail.resultError}
                />
              ) : visibleScenarioDetail.result ? (
                <>
                  <p className="text-sm font-medium">Latest run result</p>
                  <p className="text-sm text-muted-foreground">
                    Baseline estimate:{" "}
                    {formatEstimateKind(
                      visibleScenarioDetail.result.baseline_estimate_kind
                    )}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Simulated estimate:{" "}
                    {formatEstimateKind(
                      visibleScenarioDetail.result.simulated_estimate_kind
                    )}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Affected critical initiatives:{" "}
                    {
                      visibleScenarioDetail.result
                        .affected_critical_initiative_count
                    }
                  </p>
                  {visibleScenarioDetail.result.risk_score_delta !== null ? (
                    <p className="text-sm text-muted-foreground">
                      Risk score delta:{" "}
                      {visibleScenarioDetail.result.risk_score_delta.toFixed(2)}{" "}
                      (uncalibrated score semantics when marked as such)
                    </p>
                  ) : null}
                </>
              ) : (
                <EmptyState
                  title="No executed result"
                  message="Materialize scenario runs for this definition to inspect overlays."
                />
              )}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2 className="font-heading text-base leading-snug font-medium">
              AI Chief of Staff briefs
            </h2>
          </CardTitle>
          <CardDescription>
            Claims are labelled as evidence, inference, recommendation or
            limitation. Citations bind claims to evidence packages.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {data.briefsForbidden ? (
            <ErrorState
              title="Chief of Staff access denied"
              message="Requires chief_of_staff.read permission."
            />
          ) : data.briefs.items.length === 0 ? (
            <EmptyState
              title="No briefs"
              message="Generate Chief-of-Staff briefs (CLI materialize) for this tenant."
            />
          ) : (
            <ul className="space-y-2" aria-label="Chief of Staff briefs">
              {data.briefs.items.map((brief) => {
                const selected = selectedBriefId === brief.brief_id;
                return (
                  <li key={brief.brief_id}>
                    <button
                      type="button"
                      data-testid="brief-select"
                      aria-pressed={selected}
                      className="w-full rounded-md border border-border/70 px-3 py-2 text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      onClick={() => {
                        setBriefDetailLoading(true);
                        setBriefDetailError(null);
                        setBriefDetail(null);
                        setSelectedBriefId(brief.brief_id);
                      }}
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium">
                          {brief.intent.replaceAll("_", " ")}
                        </span>
                        <Badge variant="outline">{brief.generation_state}</Badge>
                        <Badge variant="secondary">
                          {brief.final_provider.replaceAll("_", " ")}
                        </Badge>
                        {brief.estimate_kind ? (
                          <Badge variant="outline">
                            {formatEstimateKind(brief.estimate_kind)}
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        Target {brief.target_type} · as of{" "}
                        {new Date(brief.as_of_at).toISOString()}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          {data.briefs.total > PAGE_SIZE ? (
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={briefOffset === 0 || sectionPaging === "briefs"}
                onClick={() =>
                  setBriefOffset((value) => Math.max(0, value - PAGE_SIZE))
                }
              >
                Previous briefs
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={
                  briefOffset + PAGE_SIZE >= data.briefs.total ||
                  sectionPaging === "briefs"
                }
                onClick={() => setBriefOffset((value) => value + PAGE_SIZE)}
              >
                Next briefs
              </Button>
            </div>
          ) : null}

          {briefDetailError ? (
            <ErrorState
              title="Brief detail failed"
              message={briefDetailError}
            />
          ) : null}

          {selectedBriefId && briefDetailLoading && !visibleBriefDetail ? (
            <LoadingState title="Loading brief evidence" />
          ) : null}

          {visibleBriefDetail ? (
            <div
              className="space-y-3 rounded-md border border-border/70 bg-muted/10 px-3 py-3"
              data-testid="brief-detail"
            >
              <p className="text-sm font-medium">Claims and citations</p>
              {visibleBriefDetail.claims.length === 0 ? (
                <EmptyState title="No claims on this brief" />
              ) : (
                <ul className="space-y-2" aria-label="Brief claims">
                  {visibleBriefDetail.claims.map((claim) => {
                    const kind = claimDisplayKind(claim.claim_type);
                    return (
                      <li
                        key={claim.claim_id}
                        className="rounded border border-border/60 px-2 py-2"
                        data-testid="brief-claim"
                      >
                        <div className="flex flex-wrap gap-2">
                          <Badge variant={claimBadgeVariant(kind)}>
                            {claimKindLabel(kind)}
                          </Badge>
                          <Badge variant="outline">{claim.support_status}</Badge>
                          <Badge variant="outline">{claim.authorship}</Badge>
                        </div>
                        <p className="mt-1 text-sm">{claim.text}</p>
                      </li>
                    );
                  })}
                </ul>
              )}
              {visibleBriefDetail.citations.length > 0 ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    Citations ({visibleBriefDetail.citations.length})
                  </p>
                  <ul className="mt-1 space-y-1" aria-label="Brief citations">
                    {visibleBriefDetail.citations.slice(0, 20).map((citation) => (
                      <li
                        key={citation.citation_id}
                        className="text-xs text-muted-foreground"
                        data-testid="brief-citation"
                      >
                        {citation.evidence_type} → claim {citation.claim_id}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
