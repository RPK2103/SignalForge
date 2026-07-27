import { execFileSync, spawn } from "node:child_process";
import fs from "node:fs";

import {
  BACKEND_HOST,
  BACKEND_PID_FILE,
  BACKEND_PORT,
  BACKEND_ROOT,
  BACKEND_URL,
  E2E_DATABASE_URL,
  E2E_DB_PATH,
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
  // 2. Seed deterministic catalog + scenarios.
  runBackendCommand(["-m", "app.db.seed"]);

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
