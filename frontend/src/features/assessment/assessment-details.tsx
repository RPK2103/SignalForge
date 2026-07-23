"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { DecisionTraceEntry, SkillGap } from "@/lib/api/contracts/catalog";

type DecisionTraceSectionProps = {
  entries: DecisionTraceEntry[];
};

export function DecisionTraceSection({ entries }: DecisionTraceSectionProps) {
  const [expanded, setExpanded] = useState(false);

  if (entries.length === 0) return null;

  return (
    <section aria-label="Decision trace" className="rounded-lg border p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Decision Trace</h3>
          <p className="text-xs text-muted-foreground">
            Expand to review deterministic scoring contributions.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          aria-expanded={expanded}
          className="text-sm font-medium text-primary hover:underline"
        >
          {expanded ? "Hide trace" : `Show ${entries.length} entries`}
        </button>
      </div>
      {expanded ? (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-xs">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-2 pr-3">Step</th>
                <th className="py-2 pr-3">Component</th>
                <th className="py-2 pr-3">Label</th>
                <th className="py-2 pr-3">Value</th>
                <th className="py-2 pr-3">Contribution</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, index) => (
                <tr key={`${entry.step}-${entry.component}-${entry.label}-${index}`} className="border-b">
                  <td className="py-2 pr-3">{entry.step}</td>
                  <td className="py-2 pr-3">{entry.component}</td>
                  <td className="py-2 pr-3">{entry.label}</td>
                  <td className="py-2 pr-3">{entry.value}</td>
                  <td className="py-2 pr-3 tabular-nums">{entry.contribution}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}

type SkillGapsSectionProps = {
  gaps: SkillGap[];
};

export function SkillGapsSection({ gaps }: SkillGapsSectionProps) {
  if (gaps.length === 0) return null;

  return (
    <section aria-label="Skill gaps" className="rounded-lg border p-4">
      <h3 className="text-sm font-semibold">Skill Gaps</h3>
      <ul className="mt-3 space-y-2">
        {gaps.map((gap) => (
          <li
            key={gap.capability_id}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/20 px-3 py-2 text-sm"
          >
            <span>
              {gap.capability_name}{" "}
              <span className="text-muted-foreground">({gap.level})</span>
            </span>
            {gap.is_critical ? (
              <Badge variant="outline" className="border-rose-200 text-rose-700">
                Critical
              </Badge>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
