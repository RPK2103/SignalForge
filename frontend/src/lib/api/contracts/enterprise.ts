export type PageResponse<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type Organization = {
  organization_id: string;
  tenant_id: string;
  name: string;
  slug: string;
  organization_type: string;
  timezone_name: string;
};

export type DemoTenantSummary = {
  tenant_id: string;
  organization_id: string | null;
  counts: Record<string, number>;
};

export type Initiative = {
  initiative_id: string;
  tenant_id: string;
  organization_id: string;
  name: string;
  slug: string;
  description: string | null;
  strategic_priority: string;
  criticality: string;
  status: string;
};

export type GraphSummary = {
  tenant_id: string;
  projection_version: string;
  node_count: number;
  edge_count: number;
  active_edge_count: number;
  nodes_by_type: Record<string, number>;
  edges_by_type: Record<string, number>;
  edges_by_origin: Record<string, number>;
  active_finding_count: number;
  findings_by_type: Record<string, number>;
  latest_projection_run_id: string | null;
  latest_analysis_run_id: string | null;
  as_of: string;
};

export type GraphFinding = {
  graph_finding_id: string;
  tenant_id: string;
  finding_type: string;
  status: string;
  severity: string;
  confidence: number;
  title: string;
  explanation: string;
  primary_node_id: string;
  rule_id: string;
  detected_at: string;
};
