import { afterEach, describe, expect, it, vi } from "vitest";

import { apiGet, apiPostJson, apiPostNoBody } from "@/lib/api/client";
import { normalizeBaseUrl } from "@/lib/api/config";

const BASE = "http://127.0.0.1:8000";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("normalizeBaseUrl", () => {
  it("strips trailing slashes", () => {
    expect(normalizeBaseUrl("http://127.0.0.1:8000/")).toBe(
      "http://127.0.0.1:8000"
    );
  });

  it("preserves url without trailing slash", () => {
    expect(normalizeBaseUrl("http://127.0.0.1:8000")).toBe(
      "http://127.0.0.1:8000"
    );
  });
});

describe("apiClient", () => {
  it("performs GET requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiGet<{ ok: boolean }>("/api/v2/projects", {
      baseUrl: BASE,
    });

    expect(result.ok).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(
      `${BASE}/api/v2/projects`,
      expect.objectContaining({ method: "GET" })
    );
  });

  it("performs JSON POST requests", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ id: "1" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiPostJson("/api/v2/readiness/assess", { project_id: "p1" }, {
      baseUrl: BASE,
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ project_id: "p1" }));
  });

  it("performs no-body POST without Content-Type", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ brief: {} }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiPostNoBody("/api/v2/assessments/abc/leadership-brief", {
      baseUrl: BASE,
    });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.body).toBeUndefined();
    expect(init.headers.get("Content-Type")).toBeNull();
  });

  it("parses 404 API errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        text: async () =>
          JSON.stringify({
            detail: "Record not found",
            status_code: 404,
            error_type: "record_not_found",
          }),
      })
    );

    await expect(
      apiGet("/api/v2/assessments/missing", { baseUrl: BASE })
    ).rejects.toMatchObject({
      category: "not_found",
      statusCode: 404,
    });
  });

  it("parses 409 conflict errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        text: async () =>
          JSON.stringify({
            detail: "Conflict",
            status_code: 409,
            error_type: "persistence_conflict",
          }),
      })
    );

    await expect(
      apiPostJson("/api/v2/assessments", {}, { baseUrl: BASE })
    ).rejects.toMatchObject({ category: "conflict" });
  });

  it("parses 415 unsupported media type", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 415,
        text: async () =>
          JSON.stringify({
            detail: "Unsupported",
            status_code: 415,
            error_type: "unsupported_media_type",
          }),
      })
    );

    await expect(
      apiPostJson("/api/v2/assessments", {}, { baseUrl: BASE })
    ).rejects.toMatchObject({ category: "unsupported_media_type" });
  });

  it("parses 422 validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        text: async () =>
          JSON.stringify({
            detail: [{ msg: "Invalid" }],
            status_code: 422,
            error_type: "validation_error",
          }),
      })
    );

    await expect(
      apiPostJson("/api/v2/assessments", {}, { baseUrl: BASE })
    ).rejects.toMatchObject({ category: "validation_error" });
  });

  it("parses 500 snapshot integrity errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () =>
          JSON.stringify({
            detail: "Hash mismatch",
            status_code: 500,
            error_type: "snapshot_integrity_error",
          }),
      })
    );

    await expect(
      apiGet("/api/v2/assessments/1", { baseUrl: BASE })
    ).rejects.toMatchObject({ category: "snapshot_integrity_error" });
  });

  it("parses 503 database unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        text: async () =>
          JSON.stringify({
            detail: "Database unavailable",
            status_code: 503,
            error_type: "database_unavailable",
          }),
      })
    );

    await expect(
      apiGet("/api/v2/assessments", { baseUrl: BASE })
    ).rejects.toMatchObject({ category: "database_unavailable" });
  });

  it("handles malformed non-JSON errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        text: async () => "Internal Server Error",
      })
    );

    await expect(
      apiGet("/api/v2/projects", { baseUrl: BASE })
    ).rejects.toMatchObject({ category: "unknown_error" });
  });

  it("classifies network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(
      apiGet("/api/v2/projects", { baseUrl: BASE })
    ).rejects.toMatchObject({ category: "network_error" });
  });

  it("classifies aborted requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError"))
    );

    const controller = new AbortController();
    controller.abort();

    await expect(
      apiGet("/api/v2/projects", { baseUrl: BASE, signal: controller.signal })
    ).rejects.toMatchObject({ category: "api_error" });
  });

  it("does not send secret headers", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({}),
    });
    vi.stubGlobal("fetch", fetchMock);

    await apiGet("/api/v2/projects", { baseUrl: BASE });
    const [, init] = fetchMock.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("x-api-key")).toBeNull();
  });
});
