import { defineConfig, devices } from "@playwright/test";

import { BACKEND_URL, FRONTEND_HOST, FRONTEND_PORT, FRONTEND_URL } from "./e2e/constants";

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: "./e2e",
  testMatch: /.*\.spec\.ts$/,
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: false,
  workers: 1,
  forbidOnly: isCI,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: FRONTEND_URL,
    // Artifacts only on failure to keep the repo and CI clean.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Build the production frontend with the disposable backend URL baked in
  // (NEXT_PUBLIC_* is inlined at build time), then serve it.
  webServer: {
    command: `npm run build && npm run start -- --hostname ${FRONTEND_HOST} --port ${FRONTEND_PORT}`,
    url: FRONTEND_URL,
    reuseExistingServer: !isCI,
    timeout: 240_000,
    env: {
      NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL: BACKEND_URL,
    },
  },
});
