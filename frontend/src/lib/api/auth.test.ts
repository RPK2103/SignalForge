import { afterEach, describe, expect, it, vi } from "vitest";

import {
  clearSession,
  getSelectedTenant,
  isSignedIn,
  setAccessToken,
  setSelectedTenant,
  setTokenProvider,
} from "@/lib/api/auth";
import { apiGet } from "@/lib/api/client";

const BASE = "http://127.0.0.1:8000";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  clearSession();
  setTokenProvider(null);
  delete (window as unknown as Record<string, unknown>)["__SIGNALFORGE_TEST_AUTH__"];
});

function okFetch() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    text: async () => JSON.stringify({ ok: true }),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("auth boundary", () => {
  it("attaches an in-memory bearer token", async () => {
    setAccessToken("abc.def.ghi");
    const fetchMock = okFetch();
    await apiGet("/api/v3/connectors", { baseUrl: BASE });
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer abc.def.ghi");
  });

  it("attaches the selected tenant header", async () => {
    setAccessToken("t");
    setSelectedTenant("novabank");
    const fetchMock = okFetch();
    await apiGet("/api/v3/security/audit-events", { baseUrl: BASE });
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get("X-SignalForge-Tenant-ID")).toBe("novabank");
  });

  it("prefers a registered token provider", async () => {
    setTokenProvider(() => "provided-token");
    const fetchMock = okFetch();
    await apiGet("/api/v3/connectors", { baseUrl: BASE });
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer provided-token");
  });

  it("reads a test-only injected token from window", async () => {
    (window as unknown as Record<string, unknown>)["__SIGNALFORGE_TEST_AUTH__"] = {
      token: "injected",
      tenantId: "acme",
    };
    const fetchMock = okFetch();
    await apiGet("/api/v3/connectors", { baseUrl: BASE });
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get("Authorization")).toBe("Bearer injected");
    expect(getSelectedTenant()).toBe("acme");
  });

  it("sends no Authorization header when signed out", async () => {
    const fetchMock = okFetch();
    await apiGet("/api/v3/connectors", { baseUrl: BASE });
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Headers).get("Authorization")).toBeNull();
    expect(isSignedIn()).toBe(false);
  });

  it("categorizes 401 as unauthorized", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        text: async () =>
          JSON.stringify({
            detail: "Authentication required",
            status_code: 401,
            error_type: "authentication_failed",
          }),
      })
    );
    await expect(apiGet("/api/v3/connectors", { baseUrl: BASE })).rejects.toMatchObject({
      category: "unauthorized",
    });
  });

  it("categorizes 403 as forbidden", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 403,
        text: async () =>
          JSON.stringify({
            detail: "Access denied",
            status_code: 403,
            error_type: "authorization_denied",
          }),
      })
    );
    await expect(apiGet("/api/v3/security/audit-events", { baseUrl: BASE })).rejects.toMatchObject(
      { category: "forbidden" }
    );
  });
});
