import fs from "node:fs";

import { test, expect, type ConsoleMessage, type Request } from "@playwright/test";

import {
  BACKEND_URL,
  E2E_AUTH_TOKEN_FILE,
  E2E_READER_TOKEN_FILE,
  FRONTEND_URL,
  LEGACY_PROTECTED_ROUTE,
} from "./constants";

type E2eAuth = { token: string; tenantId: string };

function readE2eAuth(): E2eAuth {
  const raw = fs.readFileSync(E2E_AUTH_TOKEN_FILE, "utf-8");
  return JSON.parse(raw) as E2eAuth;
}

function readReaderAuth(): E2eAuth {
  const raw = fs.readFileSync(E2E_READER_TOKEN_FILE, "utf-8");
  return JSON.parse(raw) as E2eAuth;
}

// Inject the short-lived signed JWT into the browser BEFORE any app script runs,
// so the API client attaches it as a bearer token. The token is never stored in
// localStorage or a NEXT_PUBLIC_* variable.
test.beforeEach(async ({ page }) => {
  const auth = readE2eAuth();
  await page.addInitScript((injected) => {
    (window as unknown as Record<string, unknown>)["__SIGNALFORGE_TEST_AUTH__"] =
      injected;
  }, auth);
});

/**
 * Deterministic cross-service E2E for the SignalForge dashboard.
 *
 * Backing stack (provisioned in global-setup):
 *  - disposable SQLite database, migrated with Alembic and explicitly seeded
 *  - backend started locally with AI_ENABLED=false (deterministic fallback only)
 *  - production frontend build/start with the backend URL baked in
 *
 * The flow uses semantic selectors and seeded-but-dynamically-discovered records
 * (no hardcoded UUIDs).
 */

function readinessConfidenceFrom(text: string): { readiness: number; confidence: number } {
  const match = text.match(/Readiness\s+(\d+)\s+·\s+Confidence\s+(\d+)/);
  if (!match) {
    throw new Error(`Could not parse readiness/confidence from: ${text}`);
  }
  return { readiness: Number(match[1]), confidence: Number(match[2]) };
}

test("dashboard readiness, review, brief and simulation flow", async ({ page }) => {
  const consoleErrors: string[] = [];
  const failedRequests: string[] = [];

  page.on("console", (message: ConsoleMessage) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(`pageerror: ${error.message}`);
  });
  page.on("requestfailed", (request: Request) => {
    const failure = request.failure();
    // AbortController cancellations are expected (catalog refetch) and benign.
    if (failure && failure.errorText === "net::ERR_ABORTED") {
      return;
    }
    const url = request.url();
    if (url.startsWith(BACKEND_URL) || url.startsWith(FRONTEND_URL)) {
      failedRequests.push(`${request.method()} ${url} -> ${failure?.errorText}`);
    }
  });

  // 1. Open the dashboard.
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Assessment Setup" })).toBeVisible();

  // 2. Confirm projects and engineers load.
  const projectSelect = page.locator("#project-select");
  await expect(projectSelect).toBeVisible();
  await expect(projectSelect.locator("option")).not.toHaveCount(1);
  const engineerCheckboxes = page.getByRole("checkbox", { name: /^Select / });
  await expect(engineerCheckboxes.first()).toBeVisible();
  const engineerCount = await engineerCheckboxes.count();
  expect(engineerCount).toBeGreaterThanOrEqual(2);

  // 3. Select a seeded project.
  await projectSelect.selectOption({ index: 1 });

  // 4. Select engineers (first two).
  await engineerCheckboxes.nth(0).check();
  await engineerCheckboxes.nth(1).check();

  // 5. Run and save an assessment.
  await page.getByRole("button", { name: "Run and save assessment" }).click();
  await expect(page.getByText(/Persisted assessment · record/)).toBeVisible();

  // 7 + 8. Open assessment history and the persisted detail.
  const historySection = page.locator('section[aria-label="Assessment history"]');
  await expect(historySection).toBeVisible();
  await historySection.getByRole("button", { name: /Readiness \d+/ }).first().click();

  const detailPanel = historySection.getByText(/Readiness \d+ · Confidence \d+/);
  await expect(detailPanel).toBeVisible();
  await expect(historySection.getByText("Record ID:")).toBeVisible();
  const before = readinessConfidenceFrom((await detailPanel.textContent()) ?? "");

  // 6. Verify readiness and confidence are present and sane.
  expect(before.readiness).toBeGreaterThanOrEqual(0);
  expect(before.readiness).toBeLessThanOrEqual(100);
  expect(before.confidence).toBeGreaterThanOrEqual(0);
  expect(before.confidence).toBeLessThanOrEqual(100);

  // 9. Add an accepted review (dialog defaults to "accepted").
  await historySection.getByRole("button", { name: "Submit human review" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("heading", { name: "Submit human review" })).toBeVisible();
  await dialog.getByRole("button", { name: "Submit review" }).click();
  await expect(dialog).toBeHidden();

  // 10. Confirm deterministic scores remain unchanged after review.
  await expect(historySection.getByText(/accepted/i).first()).toBeVisible();
  const after = readinessConfidenceFrom((await detailPanel.textContent()) ?? "");
  expect(after.readiness).toBe(before.readiness);
  expect(after.confidence).toBe(before.confidence);

  // 11. Generate a Leadership Brief.
  await page.getByRole("button", { name: "Generate Leadership Brief" }).click();

  // 12 + 13. Verify deterministic fallback and ai_disabled provenance.
  await expect(page.getByText("Deterministic fallback brief")).toBeVisible();
  await expect(page.getByText(/Fallback reason:\s*ai disabled/i)).toBeVisible();

  // 14. Run a remove-engineer simulation.
  await page.getByRole("tab", { name: "Simulation" }).click();
  const simulationSection = page.locator('section[aria-label="Team simulation"]');
  await expect(simulationSection).toBeVisible();
  await expect(simulationSection.locator("#sim-operation")).toHaveValue("remove");
  await simulationSection.locator("#sim-engineer").selectOption({ index: 1 });
  await simulationSection.getByRole("button", { name: "Run simulation preview" }).click();

  // 15. Verify a readiness delta is reported by the backend.
  await expect(simulationSection.getByText(/Readiness delta:/)).toBeVisible();
  await expect(
    simulationSection.getByText("Compute-only preview", { exact: true })
  ).toBeVisible();

  // 16. Save the simulation.
  await simulationSection.getByRole("button", { name: "Save simulation" }).click();
  await expect(simulationSection.getByText("Persisted simulation record")).toBeVisible();

  // 17 + 18. Open simulation history and a persisted detail.
  const historyButton = simulationSection
    .getByRole("button", { name: /Δ readiness/ })
    .first();
  await expect(historyButton).toBeVisible();
  await historyButton.click();
  await expect(simulationSection.getByText(/Simulation ID:/)).toBeVisible();
  await expect(simulationSection.getByText("Persisted simulation record")).toBeVisible();

  // 19 + 20. No uncaught console errors and no unhandled failed requests.
  expect(consoleErrors, `Console errors:\n${consoleErrors.join("\n")}`).toEqual([]);
  expect(failedRequests, `Failed requests:\n${failedRequests.join("\n")}`).toEqual([]);
});

test("protected API rejects unauthenticated requests (401)", async ({ request }) => {
  // The bare request context carries no bearer token, so the protected API must
  // fail closed with 401 (the tenant header alone never authenticates).
  const response = await request.get(`${BACKEND_URL}/api/v3/connectors`);
  expect(response.status()).toBe(401);
  expect(response.headers()["www-authenticate"]).toBe("Bearer");
});

test("public health endpoint stays reachable without auth", async ({ request }) => {
  // `/health` is on the explicit public allowlist and must remain open.
  const response = await request.get(`${BACKEND_URL}/health`);
  expect(response.status()).toBe(200);
});

test("legacy root route is now behind default-deny auth (401)", async ({ request }) => {
  // Under default-deny, legacy root routes are no longer public: no bearer token
  // must fail closed with 401 rather than executing the deterministic compute.
  const response = await request.post(`${BACKEND_URL}${LEGACY_PROTECTED_ROUTE}`, {
    data: { project_name: "Azure AI Migration", remove_engineers: ["Kavi"] },
  });
  expect(response.status()).toBe(401);
});

test("no silent unauthenticated demo fallback for catalog data", async ({ request }) => {
  // The dashboard loads its catalog from `/api/v2/projects`. Without a token the
  // API must fail closed (401) — there is no anonymous demo data path.
  const response = await request.get(`${BACKEND_URL}/api/v2/projects`);
  expect(response.status()).toBe(401);
});

test("authenticated-but-unauthorized role is forbidden (403)", async ({ request }) => {
  // A read-only `executive_reader` lacks scenarios.run, so an authenticated
  // request to the legacy simulate route must be denied with 403 (not 401/200).
  const reader = readReaderAuth();
  const response = await request.post(`${BACKEND_URL}${LEGACY_PROTECTED_ROUTE}`, {
    headers: {
      Authorization: `Bearer ${reader.token}`,
      "X-SignalForge-Tenant-ID": reader.tenantId,
    },
    data: { project_name: "Azure AI Migration", remove_engineers: ["Kavi"] },
  });
  expect(response.status()).toBe(403);
});

test("executive briefing NovaBank narrative is authenticated and evidence-backed", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (message: ConsoleMessage) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  page.on("pageerror", (error) => {
    consoleErrors.push(`pageerror: ${error.message}`);
  });

  // Protected product route: without auth the APIs fail closed; with tenant_admin
  // the briefing surface loads live NovaBank data (no mock fallback).
  await page.goto("/briefing");
  await expect(page.getByRole("heading", { name: "Executive briefing" })).toBeVisible();
  await expect(page.getByTestId("executive-briefing-panel")).toBeVisible({
    timeout: 60_000,
  });
  await expect(page.getByTestId("synthetic-demo-banner")).toBeVisible();
  await expect(page.getByText(/fictional composite organization/i)).toBeVisible();

  // Discover initiatives from the API (no hardcoded generated IDs).
  await expect(page.getByTestId("initiative-row").first()).toBeVisible();

  // Scenario path.
  const scenario = page.getByTestId("scenario-select").first();
  await expect(scenario).toBeVisible();
  await scenario.click();
  await expect(page.getByTestId("scenario-detail")).toBeVisible();
  await expect(
    page.getByText(/uncalibrated score \(not a probability\)/i).first()
  ).toBeVisible();

  // Chief-of-Staff brief with evidence/citation labels.
  const brief = page.getByTestId("brief-select").first();
  await expect(brief).toBeVisible();
  await brief.click();
  await expect(page.getByTestId("brief-detail")).toBeVisible();
  await expect(page.getByTestId("brief-claim").first()).toBeVisible();
  await expect(page.getByText("Evidence").first()).toBeVisible();
  await expect(page.getByTestId("brief-citation").first()).toBeVisible();

  expect(consoleErrors, `Console errors:\n${consoleErrors.join("\n")}`).toEqual([]);
});

test("executive briefing route rejects unauthenticated API access", async ({
  request,
}) => {
  const response = await request.get(`${BACKEND_URL}/api/v3/organization`, {
    headers: { "X-SignalForge-Tenant-ID": "novabank" },
  });
  expect(response.status()).toBe(401);
});
