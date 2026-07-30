import path from "node:path";
import os from "node:os";

// Fixed, uncommon ports for the disposable E2E stack. Kept out of the usual
// dev ranges (3000 / 8000) to avoid clashing with a running dev environment.
export const BACKEND_PORT = 8756;
export const FRONTEND_PORT = 3799;

export const BACKEND_HOST = "127.0.0.1";
export const FRONTEND_HOST = "127.0.0.1";

export const BACKEND_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`;
export const FRONTEND_URL = `http://${FRONTEND_HOST}:${FRONTEND_PORT}`;

// Repo layout: frontend/e2e/constants.ts -> frontend/ -> repo root -> backend/
export const FRONTEND_ROOT = path.resolve(__dirname, "..");
export const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");
export const BACKEND_ROOT = path.resolve(REPO_ROOT, "backend");

// Disposable SQLite database lives in the OS temp dir, never inside the repo.
export const E2E_DB_PATH = path.join(os.tmpdir(), "signalforge_e2e.db");
// Alembic/SQLAlchemy expect forward-slash URLs even on Windows.
export const E2E_DATABASE_URL = `sqlite:///${E2E_DB_PATH.replace(/\\/g, "/")}`;

// File used to hand the backend process id from global-setup to global-teardown.
export const BACKEND_PID_FILE = path.join(os.tmpdir(), "signalforge_e2e_backend.pid");

// Test-only local-development signing secret + minted token handoff file. The
// secret is disposable and used ONLY for the E2E stack; production rejects the
// local_development auth mode entirely.
export const E2E_LOCAL_AUTH_SECRET =
  "e2e-local-development-signing-secret-do-not-use-in-prod";
export const E2E_AUTH_TOKEN_FILE = path.join(
  os.tmpdir(),
  "signalforge_e2e_auth.json"
);
// A second minted token for a read-only principal, used to prove that an
// authenticated-but-unauthorized role is denied (403) on a sensitive mutation.
export const E2E_READER_TOKEN_FILE = path.join(
  os.tmpdir(),
  "signalforge_e2e_reader_auth.json"
);
export const E2E_TENANT_ID = "novabank";

// One representative legacy root route (mounted in main.py) used to prove the
// default-deny boundary now covers the legacy surface. `/simulate` requires
// scenarios.run, so it also doubles as the forbidden-role (403) probe.
export const LEGACY_PROTECTED_ROUTE = "/simulate";

// Python interpreter (overridable in CI).
export const PYTHON_BIN = process.env.SIGNALFORGE_PYTHON ?? "python";
