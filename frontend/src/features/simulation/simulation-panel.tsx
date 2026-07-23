"use client";

import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/async-state";
import type { EngineerProfile } from "@/lib/api/contracts/catalog";
import type {
  SimulationHistoryItem,
  SimulationRecordResponse,
} from "@/lib/api/contracts/simulation-records";
import type {
  SimulationOperation,
  SimulationResponse,
} from "@/lib/api/contracts/simulations";
import { deltaDirection, formatDelta, formatDateTime } from "@/lib/display-formatters";
import { cn } from "@/lib/utils";

type SimulationPanelProps = {
  engineers: EngineerProfile[];
  baselineEngineerIds: string[];
  simulationResult: SimulationResponse | null;
  simulationRecord: SimulationRecordResponse | null;
  historyItems: SimulationHistoryItem[];
  historyTotal: number;
  isRunning: boolean;
  isPersisting: boolean;
  isHistoryLoading: boolean;
  errorMessage?: string | null;
  onRun: (operation: SimulationOperation) => void;
  onPersist: () => void;
  onSelectHistory: (recordId: string) => void;
  selectedHistoryId?: string | null;
  onRetryHistory?: () => void;
};

export function SimulationPanel({
  engineers,
  baselineEngineerIds,
  simulationResult,
  simulationRecord,
  historyItems,
  historyTotal,
  isRunning,
  isPersisting,
  isHistoryLoading,
  errorMessage,
  onRun,
  onPersist,
  onSelectHistory,
  selectedHistoryId,
  onRetryHistory,
}: SimulationPanelProps) {
  const [operationType, setOperationType] =
    useState<SimulationOperation["type"]>("remove");
  const [engineerId, setEngineerId] = useState("");
  const [removeEngineerId, setRemoveEngineerId] = useState("");
  const [addEngineerId, setAddEngineerId] = useState("");
  const [compareIds, setCompareIds] = useState<string[]>([]);

  const availableEngineers = useMemo(
    () => engineers.filter((engineer) => !baselineEngineerIds.includes(engineer.id)),
    [engineers, baselineEngineerIds]
  );

  const buildOperation = (): SimulationOperation | null => {
    switch (operationType) {
      case "add":
        return engineerId ? { type: "add", engineer_id: engineerId } : null;
      case "remove":
        return engineerId ? { type: "remove", engineer_id: engineerId } : null;
      case "replace":
        return removeEngineerId && addEngineerId
          ? {
              type: "replace",
              remove_engineer_id: removeEngineerId,
              add_engineer_id: addEngineerId,
            }
          : null;
      case "compare":
        return { type: "compare", proposed_engineer_ids: compareIds };
      default:
        return null;
    }
  };

  const handleRun = () => {
    const operation = buildOperation();
    if (operation) onRun(operation);
  };

  const activeResult = simulationRecord?.result ?? simulationResult;

  return (
    <section aria-label="Team simulation" className="space-y-4 rounded-lg border p-4">
      <div>
        <h3 className="text-sm font-semibold">Team Simulation</h3>
        <p className="text-xs text-muted-foreground">
          Compute-only preview or explicitly save simulations. Deltas come from the backend.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor="sim-operation" className="text-sm font-medium">
            Operation
          </label>
          <select
            id="sim-operation"
            value={operationType}
            onChange={(event) =>
              setOperationType(event.target.value as SimulationOperation["type"])
            }
            className="h-10 w-full rounded-md border px-3 text-sm"
          >
            <option value="add">Add engineer</option>
            <option value="remove">Remove engineer</option>
            <option value="replace">Replace engineer</option>
            <option value="compare">Compare team</option>
          </select>
        </div>

        {operationType === "add" || operationType === "remove" ? (
          <div className="space-y-2">
            <label htmlFor="sim-engineer" className="text-sm font-medium">
              Engineer
            </label>
            <select
              id="sim-engineer"
              value={engineerId}
              onChange={(event) => setEngineerId(event.target.value)}
              className="h-10 w-full rounded-md border px-3 text-sm"
            >
              <option value="">Select engineer…</option>
              {(operationType === "remove" ? engineers.filter((e) => baselineEngineerIds.includes(e.id)) : availableEngineers).map(
                (engineer) => (
                  <option key={engineer.id} value={engineer.id}>
                    {engineer.name}
                  </option>
                )
              )}
            </select>
          </div>
        ) : null}

        {operationType === "replace" ? (
          <>
            <div className="space-y-2">
              <label htmlFor="sim-remove" className="text-sm font-medium">
                Remove
              </label>
              <select
                id="sim-remove"
                value={removeEngineerId}
                onChange={(event) => setRemoveEngineerId(event.target.value)}
                className="h-10 w-full rounded-md border px-3 text-sm"
              >
                <option value="">Select engineer…</option>
                {engineers
                  .filter((engineer) => baselineEngineerIds.includes(engineer.id))
                  .map((engineer) => (
                    <option key={engineer.id} value={engineer.id}>
                      {engineer.name}
                    </option>
                  ))}
              </select>
            </div>
            <div className="space-y-2">
              <label htmlFor="sim-add" className="text-sm font-medium">
                Add
              </label>
              <select
                id="sim-add"
                value={addEngineerId}
                onChange={(event) => setAddEngineerId(event.target.value)}
                className="h-10 w-full rounded-md border px-3 text-sm"
              >
                <option value="">Select engineer…</option>
                {availableEngineers.map((engineer) => (
                  <option key={engineer.id} value={engineer.id}>
                    {engineer.name}
                  </option>
                ))}
              </select>
            </div>
          </>
        ) : null}

        {operationType === "compare" ? (
          <div className="space-y-2 md:col-span-2">
            <p className="text-sm font-medium">Proposed team</p>
            <div className="grid gap-2 sm:grid-cols-2">
              {engineers.map((engineer) => (
                <label key={engineer.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={compareIds.includes(engineer.id)}
                    onChange={() =>
                      setCompareIds((current) =>
                        current.includes(engineer.id)
                          ? current.filter((id) => id !== engineer.id)
                          : [...current, engineer.id]
                      )
                    }
                  />
                  {engineer.name}
                </label>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={handleRun} disabled={isRunning}>
          {isRunning ? "Running simulation…" : "Run simulation preview"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={onPersist}
          disabled={!simulationResult || isPersisting}
        >
          {isPersisting ? "Saving…" : "Save simulation"}
        </Button>
      </div>

      {errorMessage ? (
        <ErrorState title="Simulation failed" message={errorMessage} />
      ) : null}

      {activeResult ? (
        <div className="space-y-3 rounded-md border bg-muted/20 p-3 text-sm">
          <p>
            Simulation ID:{" "}
            <span className="font-mono text-xs">{activeResult.simulation_id}</span>
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <p>
              Readiness delta:{" "}
              <span
                className={cn(
                  "font-semibold",
                  deltaDirection(activeResult.readiness_score_delta) === "positive"
                    ? "text-emerald-700"
                    : deltaDirection(activeResult.readiness_score_delta) === "negative"
                      ? "text-rose-700"
                      : "text-muted-foreground"
                )}
              >
                {formatDelta(activeResult.readiness_score_delta)}
              </span>
            </p>
            <p>
              Confidence delta:{" "}
              <span
                className={cn(
                  "font-semibold",
                  deltaDirection(activeResult.confidence_delta) === "positive"
                    ? "text-emerald-700"
                    : deltaDirection(activeResult.confidence_delta) === "negative"
                      ? "text-rose-700"
                      : "text-muted-foreground"
                )}
              >
                {formatDelta(activeResult.confidence_delta)}
              </span>
            </p>
          </div>
          {activeResult.newly_introduced_gaps.length > 0 ? (
            <p>Introduced gaps: {activeResult.newly_introduced_gaps.length}</p>
          ) : null}
          {activeResult.resolved_gaps.length > 0 ? (
            <p>Resolved gaps: {activeResult.resolved_gaps.length}</p>
          ) : null}
          {simulationRecord ? (
            <Badge variant="secondary">Persisted simulation record</Badge>
          ) : (
            <Badge variant="outline">Compute-only preview</Badge>
          )}
        </div>
      ) : (
        <EmptyState
          title="No simulation result"
          message="Run a simulation to view backend deltas."
        />
      )}

      <div className="space-y-2">
        <h4 className="text-sm font-medium">Simulation history ({historyTotal})</h4>
        {isHistoryLoading ? (
          <LoadingState title="Loading simulation history" />
        ) : historyItems.length === 0 ? (
          <EmptyState title="No saved simulations" />
        ) : (
          <ul className="space-y-2">
            {historyItems.map((item) => (
              <li key={item.simulation_record_id}>
                <button
                  type="button"
                  onClick={() => onSelectHistory(item.simulation_record_id)}
                  className={cn(
                    "w-full rounded-md border px-3 py-2 text-left text-sm hover:bg-muted/40",
                    selectedHistoryId === item.simulation_record_id && "border-primary"
                  )}
                >
                  {item.operation_type} · Δ readiness {formatDelta(item.readiness_delta)} ·{" "}
                  {formatDateTime(item.created_at)}
                </button>
              </li>
            ))}
          </ul>
        )}
        {onRetryHistory ? (
          <Button type="button" variant="outline" size="sm" onClick={onRetryHistory}>
            Refresh history
          </Button>
        ) : null}
      </div>
    </section>
  );
}
