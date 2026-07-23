#!/usr/bin/env python3
"""Live Leadership Brief validation against a disposable SQLite database."""

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

        assessment = client.post(
            "/api/v2/assessments",
            json={"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "vikram"]},
        )
        assert assessment.status_code == 200, assessment.text
        assessment_body = assessment.json()
        record_id = assessment_body["assessment_record_id"]
        print(f"assessment_record_id={record_id}")
        print(f"assessment_id={assessment_body['assessment_id']}")

        first = client.post(f"/api/v2/assessments/{record_id}/leadership-brief")
        assert first.status_code == 200, first.text
        first_body = first.json()
        print(f"leadership_brief_record_id_1={first_body['leadership_brief_record_id']}")
        print(f"evidence_package_hash={first_body['evidence_package_hash']}")
        print(f"output_snapshot_hash={first_body['output_snapshot_hash']}")
        print(f"provider_mode={first_body['brief']['provider_mode']}")
        print(f"generation_status={first_body['brief']['generation_status']}")
        print(f"failure_category={first_body['failure_category']}")
        print(f"leadership_decision={first_body['brief']['decision']}")
        print(f"risk_count={len(first_body['brief']['top_risks'])}")
        print(f"staffing_action_count={len(first_body['brief']['staffing_actions'])}")
        print(f"mitigation_action_count={len(first_body['brief']['mitigation_actions'])}")
        print(f"evidence_reference_count={len(first_body['brief']['evidence_references'])}")

        second = client.post(f"/api/v2/assessments/{record_id}/leadership-brief")
        assert second.status_code == 200, second.text
        second_body = second.json()
        print(f"leadership_brief_record_id_2={second_body['leadership_brief_record_id']}")
        assert first_body["leadership_brief_record_id"] != second_body["leadership_brief_record_id"]
        assert first_body["output_snapshot_hash"] == second_body["output_snapshot_hash"]

        detail = client.get(f"/api/v2/assessments/{record_id}")
        assert detail.status_code == 200
        assert detail.json()["result_snapshot_hash"] == assessment_body["result_snapshot_hash"]

        listed = client.get(f"/api/v2/assessments/{record_id}/leadership-briefs")
        assert listed.status_code == 200
        assert len(listed.json()) == 2
        print("audit_event_count=2")
        print("live leadership brief validation OK")
        return 0
    except Exception as exc:
        print(f"live leadership brief validation failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
        for suffix in ("", "-wal", "-shm"):
            path = Path(f"{db_file}{suffix}")
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
