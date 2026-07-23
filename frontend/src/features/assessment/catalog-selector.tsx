"use client";

import type {
  EngineerProfile,
  ProjectProfile,
  ReadinessPolicyMetadata,
} from "@/lib/api/contracts/catalog";

import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/async-state";

type CatalogSelectorProps = {
  projects: ProjectProfile[];
  engineers: EngineerProfile[];
  policy?: ReadinessPolicyMetadata | null;
  selectedProjectId: string;
  selectedEngineerIds: string[];
  onProjectChange: (projectId: string) => void;
  onEngineerToggle: (engineerId: string) => void;
  isLoading?: boolean;
  errorMessage?: string | null;
  onRetry?: () => void;
};

export function CatalogSelector({
  projects,
  engineers,
  policy,
  selectedProjectId,
  selectedEngineerIds,
  onProjectChange,
  onEngineerToggle,
  isLoading = false,
  errorMessage,
  onRetry,
}: CatalogSelectorProps) {
  if (isLoading) {
    return (
      <LoadingState
        title="Loading catalog"
        message="Fetching projects and engineers from SignalForge…"
      />
    );
  }

  if (errorMessage) {
    return (
      <ErrorState
        title="Catalog unavailable"
        message={errorMessage}
        onRetry={onRetry}
      />
    );
  }

  if (projects.length === 0 || engineers.length === 0) {
    return (
      <EmptyState
        title="Catalog is empty"
        message="Seed the backend database or verify the API is running."
        className="space-y-3"
      />
    );
  }

  const selectedEngineers = engineers.filter((engineer) =>
    selectedEngineerIds.includes(engineer.id)
  );

  return (
    <section
      aria-label="Project and team selection"
      className="rounded-lg border border-border/70 bg-white p-4 shadow-sm"
    >
      <div className="mb-4 space-y-1">
        <h2 className="text-base font-semibold">Assessment Setup</h2>
        <p className="text-sm text-muted-foreground">
          Select a project and baseline team. All scoring comes from the backend.
        </p>
        {policy ? (
          <p className="text-xs text-muted-foreground">
            Policy {policy.version}: {policy.description}
          </p>
        ) : null}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <label htmlFor="project-select" className="text-sm font-medium">
            Project
          </label>
          <select
            id="project-select"
            value={selectedProjectId}
            onChange={(event) => onProjectChange(event.target.value)}
            className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">Select a project…</option>
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <p id="engineer-select-label" className="text-sm font-medium">
            Engineers
          </p>
          <div
            role="group"
            aria-labelledby="engineer-select-label"
            className="max-h-48 space-y-2 overflow-y-auto rounded-md border p-2"
          >
            {engineers.map((engineer) => {
              const checked = selectedEngineerIds.includes(engineer.id);
              return (
                <label
                  key={engineer.id}
                  className="flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 hover:bg-muted/50"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => onEngineerToggle(engineer.id)}
                    className="mt-1"
                    aria-label={`Select ${engineer.name}`}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{engineer.name}</span>
                    <span className="block text-xs text-muted-foreground">
                      {engineer.experience_years} years experience
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-md border bg-muted/20 p-3">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Selected team ({selectedEngineers.length})
        </p>
        {selectedEngineers.length === 0 ? (
          <p className="mt-1 text-sm text-muted-foreground">
            Choose at least one engineer to run an assessment.
          </p>
        ) : (
          <p className="mt-1 text-sm">
            {selectedEngineers.map((engineer) => engineer.name).join(", ")}
          </p>
        )}
      </div>
    </section>
  );
}

type AssessmentActionsProps = {
  onPreview: () => void;
  onPersist: () => void;
  isSubmitting: boolean;
  canSubmit: boolean;
};

export function AssessmentActions({
  onPreview,
  onPersist,
  isSubmitting,
  canSubmit,
}: AssessmentActionsProps) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button
        type="button"
        variant="outline"
        disabled={!canSubmit || isSubmitting}
        onClick={onPreview}
      >
        Preview assessment
      </Button>
      <Button
        type="button"
        disabled={!canSubmit || isSubmitting}
        onClick={onPersist}
      >
        {isSubmitting ? "Running…" : "Run and save assessment"}
      </Button>
    </div>
  );
}
