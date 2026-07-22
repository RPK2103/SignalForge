"""Live HTTP validation for v2 readiness content-type hardening."""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
VALID_BODY = json.dumps(
    {"project_id": "azure_ai_migration", "engineer_ids": ["kavi", "vikram"]}
).encode()


def get(path: str):
    with urllib.request.urlopen(BASE + path) as response:
        return response.status, response.read()


def post_raw(path: str, body: bytes, content_type: str | None):
    headers = {}
    if content_type is not None:
        headers["Content-Type"] = content_type
    request = urllib.request.Request(
        BASE + path,
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return exc.code, json.loads(payload) if payload else {}


def main() -> int:
    print("=== CONTENT-TYPE LIVE VALIDATION ===")
    failures: list[str] = []

    checks = [
        ("GET /health", lambda: get("/health")[0], 200),
        ("GET /docs", lambda: get("/docs")[0], 200),
        (
            "GET /openapi.json has 415",
            lambda: "415"
            in json.loads(get("/openapi.json")[1])["paths"][
                "/api/v2/readiness/assess"
            ]["post"]["responses"],
            True,
        ),
        (
            "POST assess application/json",
            lambda: post_raw(
                "/api/v2/readiness/assess", VALID_BODY, "application/json"
            )[0],
            200,
        ),
        (
            "POST assess text/plain",
            lambda: post_raw(
                "/api/v2/readiness/assess", VALID_BODY, "text/plain"
            )[0],
            415,
        ),
        (
            "POST assess application/xml",
            lambda: post_raw(
                "/api/v2/readiness/assess", VALID_BODY, "application/xml"
            )[0],
            415,
        ),
        (
            "POST assess malformed JSON",
            lambda: post_raw(
                "/api/v2/readiness/assess", b'{"project_id":', "application/json"
            )[0],
            422,
        ),
        (
            "Legacy POST /analyze",
            lambda: post_raw(
                "/analyze",
                json.dumps(
                    {
                        "name": "Kavi",
                        "experience": 5,
                        "skills": ["Azure"],
                        "certifications": [],
                        "projects": [],
                    }
                ).encode(),
                "application/json",
            )[0],
            200,
        ),
    ]

    for label, action, expected in checks:
        try:
            result = action()
            ok = result == expected
            print(f"{label}: {result} {'OK' if ok else f'EXPECTED {expected}'}")
            if not ok:
                failures.append(label)
        except Exception as exc:
            print(f"{label}: ERROR {exc}")
            failures.append(label)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
