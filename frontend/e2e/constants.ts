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

// Python interpreter (overridable in CI).
export const PYTHON_BIN = process.env.SIGNALFORGE_PYTHON ?? "python";
