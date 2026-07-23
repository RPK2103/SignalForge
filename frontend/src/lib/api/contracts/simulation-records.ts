import type { SimulationResponse } from "./simulations";

export type SimulationRecordResponse = {
  simulation_record_id: string;
  simulation_id: string;
  project_id: string;
  operation_type: string;
  policy_version: string;
  schema_version: string;
  created_at: string;
  input_snapshot_hash: string;
  baseline_snapshot_hash: string;
  proposed_snapshot_hash: string;
  result_snapshot_hash: string;
  result: SimulationResponse;
};

export type SimulationHistoryItem = {
  simulation_record_id: string;
  simulation_id: string;
  project_id: string;
  operation_type: string;
  readiness_delta: number;
  confidence_delta: number;
  policy_version: string;
  created_at: string;
};

export type SimulationHistoryResponse = {
  items: SimulationHistoryItem[];
  total: number;
  limit: number;
  offset: number;
};

export type CreateSimulationRecordRequest = {
  project_id: string;
  baseline_engineer_ids: string[];
  operation: SimulationResponse["operation"];
  policy_version?: string | null;
};
