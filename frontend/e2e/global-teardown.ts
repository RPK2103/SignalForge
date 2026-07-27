import { execFileSync } from "node:child_process";
import fs from "node:fs";

import { BACKEND_PID_FILE, E2E_DB_PATH } from "./constants";

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function killBackend(): void {
  if (!fs.existsSync(BACKEND_PID_FILE)) {
    return;
  }
  const pid = Number.parseInt(fs.readFileSync(BACKEND_PID_FILE, "utf-8").trim(), 10);
  if (Number.isFinite(pid)) {
    try {
      if (process.platform === "win32") {
        // Kill the whole process tree (uvicorn may spawn workers).
        execFileSync("taskkill", ["/pid", String(pid), "/T", "/F"], {
          stdio: "ignore",
        });
      } else {
        process.kill(-pid, "SIGTERM");
      }
    } catch {
      // Process already exited — nothing to clean up.
    }
  }
  fs.rmSync(BACKEND_PID_FILE, { force: true });
}

async function removeDatabaseFiles(): Promise<void> {
  // On Windows the backend can hold the SQLite file handle briefly after the
  // process is killed, so deletion is retried instead of failing the run.
  for (const suffix of ["", "-journal", "-wal", "-shm"]) {
    const file = `${E2E_DB_PATH}${suffix}`;
    for (let attempt = 0; attempt < 10; attempt += 1) {
      if (!fs.existsSync(file)) {
        break;
      }
      try {
        fs.rmSync(file, { force: true });
        break;
      } catch (error) {
        if (attempt === 9) {
          // Best-effort cleanup of a disposable temp-dir file: warn, don't fail.
          console.warn(`E2E teardown: could not delete ${file}: ${String(error)}`);
          break;
        }
        await sleep(300);
      }
    }
  }
}

async function globalTeardown(): Promise<void> {
  killBackend();
  // Give the OS a moment to release the backend's file handles before deleting.
  await sleep(500);
  await removeDatabaseFiles();
}

export default globalTeardown;
