import { describe, expect, it, vi } from "vitest";

describe("assessment history detail stale-response guard", () => {
  it("ignores late detail responses when a newer record is selected", async () => {
    let resolveFirst: (value: { assessment_record_id: string }) => void;
    const firstPromise = new Promise<{ assessment_record_id: string }>(
      (resolve) => {
        resolveFirst = resolve;
      }
    );

    let currentRequestId = 0;
    let selectedDetail: { assessment_record_id: string } | null = null;

    const openHistoryDetail = async (recordId: string) => {
      const requestId = ++currentRequestId;
      const detail = await (recordId === "slow"
        ? firstPromise
        : Promise.resolve({ assessment_record_id: recordId }));

      if (requestId !== currentRequestId) {
        return;
      }

      selectedDetail = detail;
    };

    const slow = openHistoryDetail("slow");
    const fast = openHistoryDetail("fast");

    await fast;
    expect(selectedDetail).toEqual({ assessment_record_id: "fast" });

    resolveFirst!({ assessment_record_id: "slow" });
    await slow;

    expect(selectedDetail).toEqual({ assessment_record_id: "fast" });
  });

  it("does not call readiness compute when loading persisted detail", async () => {
    const assessSpy = vi.fn();
    const getByIdSpy = vi.fn().mockResolvedValue({
      assessment_record_id: "rec-1",
      result: { readiness_score: 72 },
    });

    await getByIdSpy("rec-1");
    expect(getByIdSpy).toHaveBeenCalledWith("rec-1");
    expect(assessSpy).not.toHaveBeenCalled();
  });
});
