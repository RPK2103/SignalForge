"""Live HTTP validation for the v2 team simulation API."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765"
HOST = "127.0.0.1"
PORT = 8765


def get(path: str):
    with urllib.request.urlopen(BASE + path) as response:
        return response.status, json.loads(response.read())


def post(path: str, data: dict, content_type: str = "application/json"):
    body = json.dumps(data).encode()
    request = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read())


def post_err(path: str, data=None, content_type: str = "application/json"):
    body = data if isinstance(data, bytes) else json.dumps(data or {}).encode()
    headers = {"Content-Type": content_type} if content_type else {}
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        try:
            return exc.code, json.loads(payload)
        except json.JSONDecodeError:
            return exc.code, {"detail": payload.decode()}


def _summarize(label: str, body: dict) -> None:
    print(
        f"{label}: id={body.get('simulation_id')} "
        f"baseline={body.get('baseline_assessment', {}).get('readiness_score')} "
        f"proposed={body.get('proposed_assessment', {}).get('readiness_score')} "
        f"delta={body.get('readiness_score_delta')} "
        f"confidence_delta={body.get('confidence_delta')} "
        f"coverage_changes={len(body.get('capability_coverage_changes', []))} "
        f"introduced_gaps={len(body.get('newly_introduced_gaps', []))} "
        f"resolved_gaps={len(body.get('resolved_gaps', []))} "
        f"dependency_changes={len(body.get('key_person_dependency_changes', []))} "
        f"mitigations={len(body.get('recommended_mitigations', []))}"
    )


def _start_server() -> subprocess.Popen:
    for port in (8765, 8777, 8787):
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", HOST, "--port", str(port)],
            cwd=str(BACKEND_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        time.sleep(2)
        if process.poll() is not None:
            continue
        global BASE, PORT
        PORT = port
        BASE = f"http://{HOST}:{port}"
        print(f"Using live server at {BASE}")
        return process
    raise RuntimeError("Unable to start uvicorn on ports 8765, 8777, or 8787")


def main() -> int:
    server = _start_server()
    failures = 0
    try:
        time.sleep(2)
        print("=== LIVE SIMULATION VALIDATION ===")
        for path in ["/health", "/openapi.json", "/api/v2/projects", "/api/v2/engineers"]:
            status, _ = get(path)
            print(f"GET {path}: {status}")
            failures += status != 200
        with urllib.request.urlopen(BASE + "/docs") as response:
            docs_status = response.status
        print(f"GET /docs: {docs_status}")
        failures += docs_status != 200

        baseline_payload = {
            "project_id": "azure_ai_migration",
            "engineer_ids": ["kavi", "vikram"],
        }
        status, _ = post("/api/v2/readiness/assess", baseline_payload)
        print(f"POST /api/v2/readiness/assess: {status}")
        failures += status != 200

        remove_payload = {
            "project_id": "azure_ai_migration",
            "baseline_engineer_ids": ["kavi", "vikram"],
            "operation": {"type": "remove", "engineer_id": "kavi"},
        }
        status, remove_body = post("/api/v2/simulations", remove_payload)
        print(f"POST /api/v2/simulations remove: {status}")
        failures += status != 200
        _summarize("remove_kavi", remove_body)

        add_status, add_body = post(
            "/api/v2/simulations",
            {
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "add", "engineer_id": "arjun"},
            },
        )
        print(f"POST /api/v2/simulations add: {add_status}")
        failures += add_status != 200
        _summarize("add_arjun", add_body)

        replace_status, replace_body = post(
            "/api/v2/simulations",
            {
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {
                    "type": "replace",
                    "remove_engineer_id": "kavi",
                    "add_engineer_id": "arjun",
                },
            },
        )
        print(f"POST /api/v2/simulations replace: {replace_status}")
        failures += replace_status != 200

        compare_status, compare_body = post(
            "/api/v2/simulations",
            {
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "compare", "proposed_engineer_ids": ["kavi", "vikram"]},
            },
        )
        print(f"POST /api/v2/simulations compare unchanged: {compare_status}")
        failures += compare_status != 200
        failures += compare_body.get("readiness_score_delta") != 0

        empty_status, _ = post(
            "/api/v2/simulations",
            {
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "compare", "proposed_engineer_ids": []},
            },
        )
        print(f"POST /api/v2/simulations empty proposed team: {empty_status}")
        failures += empty_status != 200

        invalid_status, _ = post_err(
            "/api/v2/simulations",
            {
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "remove", "engineer_id": "arjun"},
            },
        )
        print(f"POST invalid removal: {invalid_status}")
        failures += invalid_status != 409

        duplicate_status, _ = post_err(
            "/api/v2/simulations",
            {
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi", "vikram"],
                "operation": {"type": "add", "engineer_id": "kavi"},
            },
        )
        print(f"POST duplicate addition: {duplicate_status}")
        failures += duplicate_status != 409

        unknown_status, _ = post_err(
            "/api/v2/simulations",
            {
                "project_id": "azure_ai_migration",
                "baseline_engineer_ids": ["kavi"],
                "operation": {"type": "add", "engineer_id": "unknown_engineer"},
            },
        )
        print(f"POST unknown engineer: {unknown_status}")
        failures += unknown_status != 404

        plain_status, _ = post_err("/api/v2/simulations", remove_payload, "text/plain")
        print(f"POST text/plain: {plain_status}")
        failures += plain_status != 415

        malformed_status, _ = post_err(
            "/api/v2/simulations",
            b"{invalid",
            "application/json",
        )
        print(f"POST malformed JSON: {malformed_status}")
        failures += malformed_status != 422

        legacy_status, legacy_body = post(
            "/simulate",
            {"project_name": "Azure AI Migration", "remove_engineers": ["Kavi"]},
        )
        print(f"POST legacy /simulate: {legacy_status}")
        failures += legacy_status != 200

        repeat_status, repeat_body = post("/api/v2/simulations", remove_payload)
        print(f"POST repeat remove deterministic: {repeat_body.get('simulation_id') == remove_body.get('simulation_id')}")
        failures += repeat_body != remove_body

        print(f"RESULT: {'PASS' if failures == 0 else 'FAIL'} ({failures} failures)")
        return 1 if failures else 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
