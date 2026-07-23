import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ReviewDialog } from "@/features/history/review-dialog";

afterEach(() => {
  cleanup();
});

describe("ReviewDialog validation", () => {
  it("requires override reason for overridden state", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <ReviewDialog open onOpenChange={() => undefined} onSubmit={onSubmit} />
    );

    await user.selectOptions(screen.getByLabelText(/review state/i), "overridden");
    await user.click(screen.getByRole("button", { name: /submit review/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/override reason/i);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("requires comment for needs_more_data", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <ReviewDialog open onOpenChange={() => undefined} onSubmit={onSubmit} />
    );

    fireEvent.change(screen.getByLabelText(/review state/i), {
      target: { value: "needs_more_data" },
    });
    await user.click(screen.getByRole("button", { name: /submit review/i }));

    const dialog = screen.getByRole("dialog", { name: /submit human review/i });
    expect(within(dialog).getByRole("alert")).toHaveTextContent(/comment is required/i);
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe("ExecutiveSummary empty state", () => {
  it("shows empty guidance without hardcoded KPIs", async () => {
    const { ExecutiveSummary } = await import(
      "@/components/dashboard/executive-summary"
    );

    render(<ExecutiveSummary kpis={[]} />);
    expect(screen.getByText(/no assessment results yet/i)).toBeInTheDocument();
  });
});
