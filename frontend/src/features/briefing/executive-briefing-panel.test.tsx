import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ExecutiveBriefingPanel } from "@/features/briefing/executive-briefing-panel";
import { SignalForgeApiError } from "@/lib/api/errors";
import { chiefOfStaffService } from "@/lib/api/services/chief-of-staff-service";
import { enterpriseService } from "@/lib/api/services/enterprise-service";
import { scenarioService } from "@/lib/api/services/scenario-service";

vi.mock("@/lib/api/services/enterprise-service", () => ({
  enterpriseService: {
    getOrganization: vi.fn(),
    listInitiatives: vi.fn(),
    getGraphSummary: vi.fn(),
    listFindings: vi.fn(),
  },
}));

vi.mock("@/lib/api/services/scenario-service", () => ({
  scenarioService: {
    listScenarios: vi.fn(),
    listRuns: vi.fn(),
    getRunResult: vi.fn(),
  },
}));

vi.mock("@/lib/api/services/chief-of-staff-service", () => ({
  chiefOfStaffService: {
    listBriefs: vi.fn(),
    getBrief: vi.fn(),
    listClaims: vi.fn(),
    listCitations: vi.fn(),
  },
}));

const mockedEnterprise = vi.mocked(enterpriseService);
const mockedScenarios = vi.mocked(scenarioService);
const mockedCos = vi.mocked(chiefOfStaffService);

function seedHappyPath() {
  mockedEnterprise.getOrganization.mockResolvedValue({
    organization_id: "org_1",
    tenant_id: "novabank",
    name: "NovaBank",
    slug: "novabank",
    organization_type: "enterprise",
    timezone_name: "UTC",
  });
  mockedEnterprise.listInitiatives.mockResolvedValue({
    items: [
      {
        initiative_id: "init_fraud",
        tenant_id: "novabank",
        organization_id: "org_1",
        name: "Fraud Detection Launch",
        slug: "fraud-detection-launch",
        description: "Synthetic story initiative",
        strategic_priority: "high",
        criticality: "critical",
        status: "active",
      },
    ],
    total: 14,
    limit: 10,
    offset: 0,
  });
  mockedEnterprise.getGraphSummary.mockResolvedValue({
    tenant_id: "novabank",
    projection_version: "v1",
    node_count: 1015,
    edge_count: 1362,
    active_edge_count: 1300,
    nodes_by_type: {
      project: 24,
      engineer: 48,
      repository: 32,
      initiative: 14,
    },
    edges_by_type: {},
    edges_by_origin: {},
    active_finding_count: 90,
    findings_by_type: {},
    latest_projection_run_id: null,
    latest_analysis_run_id: null,
    as_of: "2026-07-31T18:00:00Z",
  });
  mockedEnterprise.listFindings.mockResolvedValue({
    items: [
      {
        graph_finding_id: "find_1",
        tenant_id: "novabank",
        finding_type: "ownership_concentration",
        status: "active",
        severity: "high",
        confidence: 0.8,
        title: "Concentrated repository ownership",
        explanation: "Evidence-backed concentration finding.",
        primary_node_id: "node_1",
        rule_id: "ownership_concentration_v1",
        detected_at: "2026-07-31T18:00:00Z",
      },
    ],
    total: 1,
    limit: 10,
    offset: 0,
  });
  mockedScenarios.listScenarios.mockResolvedValue({
    items: [
      {
        scenario_definition_id: "scen_1",
        tenant_id: "novabank",
        name: "Critical engineer role transition",
        description: "Synthetic counterfactual",
        target_type: "initiative",
        target_id: "init_fraud",
        scenario_kind: "key_person_unavailable",
        lifecycle_state: "active",
        current_version: 1,
      },
    ],
    total: 1,
    limit: 10,
    offset: 0,
  });
  mockedScenarios.listRuns.mockResolvedValue({
    items: [
      {
        scenario_run_id: "run_1",
        tenant_id: "novabank",
        scenario_definition_id: "scen_1",
        scenario_version_id: "ver_1",
        target_type: "initiative",
        target_id: "init_fraud",
        state: "completed",
        run_mode: "manual",
        as_of_at: "2026-07-31T18:00:00Z",
        horizon_days: 90,
        source_fingerprint: "src_fp",
        baseline_fingerprint: "base_fp",
        scenario_fingerprint: "scen_fp",
        run_input_hash: "input_hash",
        created_at: "2026-07-31T18:00:00Z",
      },
    ],
    total: 1,
    limit: 5,
    offset: 0,
  });
  mockedScenarios.getRunResult.mockResolvedValue({
    scenario_result_id: "res_1",
    scenario_run_id: "run_1",
    tenant_id: "novabank",
    target_type: "initiative",
    target_id: "init_fraud",
    as_of_at: "2026-07-31T18:00:00Z",
    horizon_days: 90,
    scenario_kind: "key_person_unavailable",
    baseline_estimate_kind: "uncalibrated_score",
    simulated_estimate_kind: "uncalibrated_score",
    estimate_comparability: "comparable",
    baseline_probability: null,
    simulated_probability: null,
    baseline_risk_score: 40,
    simulated_risk_score: 55,
    risk_score_delta: 15,
    affected_project_count: 2,
    affected_initiative_count: 1,
    affected_critical_initiative_count: 1,
    findings_added_count: 1,
    findings_removed_count: 0,
    findings_worsened_count: 1,
    findings_improved_count: 0,
    data_quality_warnings: [],
    applicability_warnings: [],
    result_hash: "result_hash_1",
  });
  mockedCos.listBriefs.mockResolvedValue({
    items: [
      {
        brief_id: "brief_1",
        tenant_id: "novabank",
        run_id: "cos_run_1",
        evidence_snapshot_id: "snap_1",
        target_type: "initiative",
        target_id: "init_fraud",
        intent: "delivery_status_brief",
        as_of_at: "2026-07-31T18:00:00Z",
        horizon_days: 90,
        brief_json: {},
        output_hash: "abc",
        output_schema_version: "1",
        generation_state: "fallback_generated",
        final_provider: "deterministic_fallback",
        estimate_kind: "uncalibrated_score",
        probability: null,
        created_at: "2026-07-31T18:00:00Z",
      },
    ],
    total: 1,
    limit: 10,
    offset: 0,
  });
  mockedCos.getBrief.mockResolvedValue({
    brief_id: "brief_1",
    tenant_id: "novabank",
    run_id: "cos_run_1",
    evidence_snapshot_id: "snap_1",
    target_type: "initiative",
    target_id: "init_fraud",
    intent: "delivery_status_brief",
    as_of_at: "2026-07-31T18:00:00Z",
    horizon_days: 90,
    brief_json: {},
    output_hash: "abc",
    output_schema_version: "1",
    generation_state: "fallback_generated",
    final_provider: "deterministic_fallback",
    estimate_kind: "uncalibrated_score",
    probability: null,
    created_at: "2026-07-31T18:00:00Z",
  });
  mockedCos.listClaims.mockResolvedValue([
    {
      claim_id: "c1",
      claim_type: "source_fact",
      text: "Ownership concentration is present on a critical repository.",
      support_status: "supported",
      authorship: "deterministic",
      temporal_cutoff: "2026-07-31T18:00:00Z",
      evidence_ids: ["e1"],
      ordering_index: 0,
    },
    {
      claim_id: "c2",
      claim_type: "advisory_option",
      text: "Schedule a human risk review.",
      support_status: "supported",
      authorship: "deterministic",
      temporal_cutoff: "2026-07-31T18:00:00Z",
      evidence_ids: ["e1"],
      ordering_index: 1,
    },
  ]);
  mockedCos.listCitations.mockResolvedValue([
    {
      citation_id: "cit_1",
      claim_id: "c1",
      evidence_id: "e1",
      evidence_type: "graph_finding",
      package_id: "pkg_1",
      ordering_index: 0,
    },
  ]);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ExecutiveBriefingPanel", () => {
  it("renders portfolio, synthetic label, scenarios and brief evidence", async () => {
    seedHappyPath();
    const user = userEvent.setup();
    render(<ExecutiveBriefingPanel />);

    await waitFor(() =>
      expect(screen.getByTestId("executive-briefing-panel")).toBeInTheDocument()
    );
    expect(screen.getByTestId("synthetic-demo-banner")).toBeInTheDocument();
    expect(screen.getByText("Fraud Detection Launch")).toBeInTheDocument();
    expect(screen.getByText("Concentrated repository ownership")).toBeInTheDocument();

    await user.click(screen.getByTestId("scenario-select"));
    await waitFor(() =>
      expect(screen.getByTestId("scenario-detail")).toBeInTheDocument()
    );
    expect(
      screen.getAllByText(/uncalibrated score \(not a probability\)/i).length
    ).toBeGreaterThan(0);

    await user.click(screen.getByTestId("brief-select"));
    await waitFor(() =>
      expect(screen.getByTestId("brief-detail")).toBeInTheDocument()
    );
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("Recommendation")).toBeInTheDocument();
    expect(screen.getByTestId("brief-citation")).toBeInTheDocument();
  });

  it("shows unauthorized state without mock fallback", async () => {
    mockedEnterprise.getOrganization.mockRejectedValue(
      new SignalForgeApiError({
        message: "Authentication required",
        category: "unauthorized",
        statusCode: 401,
      })
    );
    render(<ExecutiveBriefingPanel />);
    await waitFor(() =>
      expect(screen.getByText(/Authentication required/i)).toBeInTheDocument()
    );
    expect(screen.queryByTestId("executive-briefing-panel")).not.toBeInTheDocument();
  });

  it("shows forbidden state", async () => {
    mockedEnterprise.getOrganization.mockRejectedValue(
      new SignalForgeApiError({
        message: "Forbidden",
        category: "forbidden",
        statusCode: 403,
      })
    );
    render(<ExecutiveBriefingPanel />);
    await waitFor(() =>
      expect(
        screen.getByText(/You do not have access to this briefing/i)
      ).toBeInTheDocument()
    );
  });

  it("shows empty states when tenant has no portfolio content", async () => {
    mockedEnterprise.getOrganization.mockResolvedValue({
      organization_id: "org_x",
      tenant_id: "acme",
      name: "Acme",
      slug: "acme",
      organization_type: "enterprise",
      timezone_name: "UTC",
    });
    mockedEnterprise.listInitiatives.mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
    });
    mockedEnterprise.getGraphSummary.mockResolvedValue({
      tenant_id: "acme",
      projection_version: "v1",
      node_count: 0,
      edge_count: 0,
      active_edge_count: 0,
      nodes_by_type: {},
      edges_by_type: {},
      edges_by_origin: {},
      active_finding_count: 0,
      findings_by_type: {},
      latest_projection_run_id: null,
      latest_analysis_run_id: null,
      as_of: "2026-07-31T18:00:00Z",
    });
    mockedEnterprise.listFindings.mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
    });
    mockedScenarios.listScenarios.mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
    });
    mockedCos.listBriefs.mockResolvedValue({
      items: [],
      total: 0,
      limit: 10,
      offset: 0,
    });

    render(<ExecutiveBriefingPanel />);
    await waitFor(() =>
      expect(screen.getByTestId("executive-briefing-panel")).toBeInTheDocument()
    );
    expect(screen.queryByTestId("synthetic-demo-banner")).not.toBeInTheDocument();
    expect(screen.getByText(/No initiatives/i)).toBeInTheDocument();
    expect(screen.getByText(/No scenarios/i)).toBeInTheDocument();
    expect(screen.getByText(/No briefs/i)).toBeInTheDocument();
  });

  it("shows scenario result errors instead of empty state", async () => {
    seedHappyPath();
    mockedScenarios.getRunResult.mockRejectedValue(
      new SignalForgeApiError({
        message: "Upstream failure",
        category: "api_error",
        statusCode: 500,
      })
    );
    const user = userEvent.setup();
    render(<ExecutiveBriefingPanel />);
    await waitFor(() =>
      expect(screen.getByTestId("executive-briefing-panel")).toBeInTheDocument()
    );
    await user.click(screen.getByTestId("scenario-select"));
    await waitFor(() =>
      expect(screen.getByText(/Scenario result unavailable/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/No executed result/i)).not.toBeInTheDocument();
  });
});
