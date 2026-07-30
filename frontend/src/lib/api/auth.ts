/**
 * Frontend authentication boundary (Phase 3 Prompt 7).
 *
 * A central access-token provider whose token lives ONLY in memory (never in
 * localStorage, never in a NEXT_PUBLIC_* variable, never hardcoded). The API
 * client asks this provider for a bearer token and the selected tenant on every
 * request. Production wires a real Entra token acquirer into `setTokenProvider`;
 * local Playwright injects a short-lived test-only signed JWT via the same seam.
 */

export type AccessTokenProvider = () => string | null | Promise<string | null>;

export type AuthState = {
  /** Bearer access token, or null when signed out. */
  token: string | null;
  /** Selected tenant id (the `X-SignalForge-Tenant-ID` selector). */
  tenantId: string | null;
};

const state: AuthState = {
  token: null,
  tenantId: null,
};

let tokenProvider: AccessTokenProvider | null = null;

/**
 * Register the production token acquirer (e.g. an Entra/MSAL adapter) or a
 * test-only adapter. The provider is consulted lazily per request so tokens can
 * refresh without re-wiring the client.
 */
export function setTokenProvider(provider: AccessTokenProvider | null): void {
  tokenProvider = provider;
}

/** Directly set an in-memory token (used by the signed-in session flow). */
export function setAccessToken(token: string | null): void {
  state.token = token;
}

export function setSelectedTenant(tenantId: string | null): void {
  state.tenantId = tenantId;
}

export function getSelectedTenant(): string | null {
  if (state.tenantId) {
    return state.tenantId;
  }
  return readInjectedTestAuth()?.tenantId ?? null;
}

export function clearSession(): void {
  state.token = null;
  state.tenantId = null;
}

export function isSignedIn(): boolean {
  return Boolean(state.token) || tokenProvider !== null;
}

type InjectedTestAuth = { token?: string; tenantId?: string };

/**
 * Test-only seam: read a token injected on `window.__SIGNALFORGE_TEST_AUTH__`.
 *
 * This is NOT a production bypass: production never sets this global, and the
 * backend rejects the local/test authentication modes that would accept such a
 * token. Local Playwright injects a short-lived signed JWT before the app loads.
 */
function readInjectedTestAuth(): InjectedTestAuth | null {
  if (typeof window === "undefined") {
    return null;
  }
  const injected = (window as unknown as Record<string, unknown>)[
    "__SIGNALFORGE_TEST_AUTH__"
  ];
  if (injected && typeof injected === "object") {
    return injected as InjectedTestAuth;
  }
  return null;
}

/** Resolve the current bearer token, preferring a registered provider. */
export async function getAccessToken(): Promise<string | null> {
  if (tokenProvider) {
    return await tokenProvider();
  }
  if (state.token) {
    return state.token;
  }
  return readInjectedTestAuth()?.token ?? null;
}
