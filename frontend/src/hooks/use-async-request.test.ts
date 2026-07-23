import { describe, expect, it } from "vitest";

import { useAsyncRequest } from "@/hooks/use-async-request";
import { renderHook, act, waitFor } from "@testing-library/react";

describe("useAsyncRequest stale response handling", () => {
  it("ignores late responses from older requests", async () => {
    let resolveFirst: (value: string) => void;
    const firstPromise = new Promise<string>((resolve) => {
      resolveFirst = resolve;
    });

    const { result } = renderHook(() => useAsyncRequest<string>());

    await act(async () => {
      void result.current.execute(() => firstPromise);
    });

    await act(async () => {
      void result.current.execute(async () => "newer");
    });

    await waitFor(() => expect(result.current.state.data).toBe("newer"));

    await act(async () => {
      resolveFirst!("older");
    });

    expect(result.current.state.data).toBe("newer");
  });
});

describe("isSimulationOperation", () => {
  it("validates discriminated simulation operations", async () => {
    const { isSimulationOperation } = await import(
      "@/lib/api/contracts/simulations"
    );

    expect(isSimulationOperation({ type: "add", engineer_id: "e1" })).toBe(true);
    expect(isSimulationOperation({ type: "remove", engineer_id: "e1" })).toBe(
      true
    );
    expect(
      isSimulationOperation({
        type: "replace",
        remove_engineer_id: "e1",
        add_engineer_id: "e2",
      })
    ).toBe(true);
    expect(
      isSimulationOperation({ type: "compare", proposed_engineer_ids: [] })
    ).toBe(true);
    expect(isSimulationOperation({ type: "add" })).toBe(false);
  });
});

describe("providerModeLabel", () => {
  it("labels azure and fallback modes distinctly", async () => {
    const { providerModeLabel } = await import(
      "@/lib/api/contracts/leadership-briefs"
    );

    expect(providerModeLabel("azure_openai")).toContain("AI-generated");
    expect(providerModeLabel("deterministic_fallback")).toContain("fallback");
  });
});
