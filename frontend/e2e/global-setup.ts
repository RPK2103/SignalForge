import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";

import {
  BACKEND_HOST,
  BACKEND_PID_FILE,
  BACKEND_PORT,
  BACKEND_ROOT,
  BACKEND_URL,
  E2E_AUTH_TOKEN_FILE,
  E2E_DATABASE_URL,
  E2E_DB_PATH,
  E2E_LOCAL_AUTH_SECRET,
  E2E_READER_TOKEN_FILE,
  E2E_TENANT_ID,
  FRONTEND_URL,
  PYTHON_BIN,
} from "./constants";

function removeDatabaseFiles(): void {
  for (const suffix of ["", "-journal", "-wal", "-shm"]) {
    const file = `${E2E_DB_PATH}${suffix}`;
    if (fs.existsSync(file)) {
      fs.rmSync(file, { force: true });
    }
  }
}

function backendEnv(): NodeJS.ProcessEnv {
  return {
    ...process.env,
    DATABASE_URL: E2E_DATABASE_URL,
    AI_ENABLED: "false",
    APP_ENV: "development",
    LOG_LEVEL: "WARNING",
    // Mandatory authentication: run the disposable backend in local_development
    // mode so the browser can present a short-lived signed JWT. Never production.
    AUTH_MODE: "local_development",
    SIGNALFORGE_LOCAL_AUTH_SECRET: E2E_LOCAL_AUTH_SECRET,
    // Allow the disposable production frontend origin through CORS.
    // pydantic-settings JSON-decodes list fields from env, so pass a JSON array.
    CORS_ORIGINS: JSON.stringify([
      FRONTEND_URL,
      `http://localhost:${new URL(FRONTEND_URL).port}`,
    ]),
    // Never let a developer .env inject real Azure credentials into the E2E run.
    AZURE_OPENAI_ENDPOINT: "",
    AZURE_OPENAI_API_KEY: "",
    AZURE_OPENAI_DEPLOYMENT: "",
  };
}

function runBackendCommand(args: string[]): void {
  execFileSync(PYTHON_BIN, args, {
    cwd: BACKEND_ROOT,
    env: backendEnv(),
    stdio: "inherit",
  });
}

/**
 * Mint a short-lived local-development JWT via the backend security CLI and hand
 * it to the Playwright spec through a temp file. The signing secret is never
 * written to disk; only the resulting token is.
 */
function mintDevToken(subject: string, roles: string): string {
  const output = execFileSync(
    PYTHON_BIN,
    [
      "-m",
      "app.security",
      "issue-dev-token",
      "--subject",
      subject,
      "--tenant",
      E2E_TENANT_ID,
      "--roles",
      roles,
      "--ttl-seconds",
      "3600",
    ],
    { cwd: BACKEND_ROOT, env: backendEnv(), encoding: "utf-8" }
  );
  return (JSON.parse(output) as { token: string }).token;
}

function mintE2eToken(): void {
  // Privileged token drives the authenticated dashboard flow.
  fs.writeFileSync(
    E2E_AUTH_TOKEN_FILE,
    JSON.stringify({
      token: mintDevToken("e2e-dashboard-user", "tenant_admin"),
      tenantId: E2E_TENANT_ID,
    }),
    "utf-8"
  );
  // Read-only token proves an authenticated-but-unauthorized role is denied 403.
  fs.writeFileSync(
    E2E_READER_TOKEN_FILE,
    JSON.stringify({
      token: mintDevToken("e2e-reader-user", "executive_reader"),
      tenantId: E2E_TENANT_ID,
    }),
    "utf-8"
  );
}

async function waitForHealth(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        return;
      }
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(
    `Backend did not become healthy at ${url} within ${timeoutMs}ms. Last error: ${String(
      lastError
    )}`
  );
}

async function globalSetup(): Promise<void> {
  removeDatabaseFiles();

  // 1. Migrate the disposable database to head.
  runBackendCommand(["-m", "alembic", "upgrade", "head"]);
  // 2. Seed deterministic Phase 2 catalog + Prompt 9 NovaBank enterprise demo.
  runBackendCommand(["-m", "app.db.seed"]);
  runBackendCommand(["-m", "app.demo", "novabank", "seed", "--json"]);
  // 2a. Materialize graph, story scenarios and deterministic Chief-of-Staff briefs
  // so the executive briefing surface can exercise the NovaBank narrative.
  runBackendCommand(["-m", "app.demo", "novabank", "materialize", "--json"]);
  // 2b. Mint the E2E bearer token for the authenticated dashboard flow.
  mintE2eToken();

  // 3. Start the backend against the disposable DB with AI disabled.
  const backend = spawn(
    PYTHON_BIN,
    [
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      BACKEND_HOST,
      "--port",
      String(BACKEND_PORT),
    ],
    {
      cwd: BACKEND_ROOT,
      env: backendEnv(),
      stdio: "inherit",
      // Own process group so teardown can reliably kill the tree.
      detached: process.platform !== "win32",
    }
  );

  if (backend.pid) {
    fs.writeFileSync(BACKEND_PID_FILE, String(backend.pid), "utf-8");
  }

  await waitForHealth(`${BACKEND_URL}/health`, 60_000);
}

export default globalSetup;
