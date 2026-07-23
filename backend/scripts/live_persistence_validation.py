#!/usr/bin/env python3
"""Live persistence validation against a disposable SQLite database."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> int:
    db_file = Path(tempfile.mkstemp(suffix=".db")[1])
    db_url = f"sqlite:///{db_file.as_posix()}"
    os.environ["DATABASE_URL"] = db_url
    os.environ["AI_ENABLED"] = "false"
    proc = None

    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "app.db.seed"],
            cwd=ROOT,
            check=True,
        )

        port = _free_port()
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=ROOT,
        )
        time.sleep(2)
        client = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10.0)

        health = client.get("/health")
        assert health.status_code == 200

        assessment = client.post(
            "/api/v2/assessments",
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "vikram"]},
        )
        assert assessment.status_code == 200, assessment.text
        body = assessment.json()
        record_id = body["assessment_record_id"]
        print(f"assessment_record_id={record_id}")
        print(f"assessment_id={body['assessment_id']}")
        print(f"result_snapshot_hash={body['result_snapshot_hash']}")

        detail = client.get(f"/api/v2/assessments/{record_id}")
        assert detail.status_code == 200

        review = client.post(
            f"/api/v2/assessments/{record_id}/reviews",
            json={"state": "accepted", "reviewer_reference": "live-validator"},
        )
        assert review.status_code == 200

        simulation = client.post(
            "/api/v2/simulation-records",
            json={
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "remove", "engineer_id": "kavi"},
            },
        )
        assert simulation.status_code == 200, simulation.text
        sim_body = simulation.json()
        print(f"simulation_record_id={sim_body['simulation_record_id']}")
        print(f"simulation_id={sim_body['simulation_id']}")

        bad_review = client.post(
            f"/api/v2/assessments/{record_id}/reviews",
            json={"state": "overridden"},
        )
        assert bad_review.status_code == 422

        bad_ct = client.post(
            "/api/v2/assessments",
            content="{}",
            headers={"Content-Type": "text/plain"},
        )
        assert bad_ct.status_code == 415

        print("live persistence validation OK")
        return 0
    except Exception as exc:
        print(f"live persistence validation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
        if db_file.exists():
            try:
                db_file.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
