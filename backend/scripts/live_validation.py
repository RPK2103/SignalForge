"""One-off live server validation script for Phase 2 review."""

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def get(path: str, parse_json: bool = True):
    with urllib.request.urlopen(BASE + path) as response:
        body = response.read()
        if parse_json:
            return response.status, json.loads(body)
        return response.status, body


def post(path: str, data: dict):
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read())


def post_err(path: str, data):
    body = data if isinstance(data, bytes) else json.dumps(data).encode()
    request = urllib.request.Request(
        BASE + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


if __name__ == "__main__":
    print("=== LIVE API VALIDATION ===")
    for path in [
        "/",
        "/health",
        "/openapi.json",
        "/api/v2/capabilities",
        "/api/v2/policies/readiness",
        "/api/v2/engineers",
        "/api/v2/projects",
    ]:
        status, _ = get(path)
        print(f"GET {path}: {status}")

    docs_status, docs_body = get("/docs", parse_json=False)
    print(f"GET /docs: {docs_status} (html, {len(docs_body)} bytes)")

    _, projects = get("/api/v2/projects")
    project_id = projects["projects"][0]["id"]
    _, engineers = get("/api/v2/engineers")
    engineer_ids = [engineer["id"] for engineer in engineers["engineers"][:2]]
    payload = {"project_id": project_id, "engineer_ids": engineer_ids}
    status, first = post("/api/v2/readiness/assess", payload)
    _, second = post("/api/v2/readiness/assess", payload)
    _, reversed_team = post(
        "/api/v2/readiness/assess",
        {"project_id": project_id, "engineer_ids": list(reversed(engineer_ids))},
    )
    _, duplicate = post(
        "/api/v2/readiness/assess",
        {"project_id": project_id, "engineer_ids": [engineer_ids[0], engineer_ids[0]]},
    )
    _, unique = post(
        "/api/v2/readiness/assess",
        {"project_id": project_id, "engineer_ids": [engineer_ids[0]]},
    )

    print(f"Catalog flow: project={project_id}, engineers={engineer_ids}")
    print(
        "Assessment:",
        f"status={status}",
        f"readiness={first['readiness_score']}",
        f"confidence={first['confidence_score']}",
        f"id={first['assessment_id']}",
    )
    print(f"Deterministic repeat: {first == second}")
    print(
        "Order independent:",
        f"score={first['readiness_score'] == reversed_team['readiness_score']}",
        f"id={first['assessment_id'] == reversed_team['assessment_id']}",
    )
    print(
        "Duplicate canonicalization:",
        f"team_len={len(duplicate['team'])}",
        f"same_id={duplicate['assessment_id'] == unique['assessment_id']}",
    )

    readiness_total = sum(
        entry["contribution"]
        for entry in first["decision_trace"]
        if entry["step"] == "readiness"
    )
    confidence_total = sum(
        entry["contribution"]
        for entry in first["decision_trace"]
        if entry["step"] == "confidence"
    )
    print(
        "Trace reconcile:",
        f"readiness={round(readiness_total, 2) == float(first['readiness_score'])}",
        f"confidence={round(confidence_total, 2) == float(first['confidence_score'])}",
    )

    for route, route_payload in [
        (
            "/analyze",
            {
                "name": "Kavi",
                "experience": 5,
                "skills": ["Azure"],
                "certifications": [],
                "projects": [],
            },
        ),
        (
            "/simulate",
            {"project_name": "Azure AI Migration", "remove_engineers": ["Kavi"]},
        ),
    ]:
        route_status, _ = post_err(route, route_payload)
        print(f"Legacy {route}: {route_status}")
