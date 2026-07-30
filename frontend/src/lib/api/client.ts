import { getAccessToken, getSelectedTenant } from "./auth";
import { buildApiUrl, getApiBaseUrl } from "./config";
import {
  SignalForgeApiError,
  categorizeErrorType,
  isAbortError,
  parseApiErrorPayload,
} from "./errors";

const TENANT_HEADER = "X-SignalForge-Tenant-ID";

export type RequestOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
  baseUrl?: string;
};

const DEFAULT_TIMEOUT_MS = 30_000;

function combineSignals(
  signals: AbortSignal[]
): { signal: AbortSignal; cleanup: () => void } {
  const controller = new AbortController();

  const onAbort = () => controller.abort();

  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort();
      break;
    }
    signal.addEventListener("abort", onAbort);
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      for (const signal of signals) {
        signal.removeEventListener("abort", onAbort);
      }
    },
  };
}

async function parseJsonResponse(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw new SignalForgeApiError({
      message: "Server returned a non-JSON response",
      category: "unknown_error",
      statusCode: response.status,
    });
  }
}

async function handleErrorResponse(response: Response): Promise<never> {
  const payload = await parseJsonResponse(response);
  const parsed = parseApiErrorPayload(payload);

  if (parsed) {
    throw new SignalForgeApiError({
      message:
        typeof parsed.detail === "string"
          ? parsed.detail
          : "Request failed",
      category: categorizeErrorType(parsed.error_type, parsed.status_code),
      statusCode: parsed.status_code,
      errorType: parsed.error_type,
      detail: parsed.detail,
    });
  }

  throw new SignalForgeApiError({
    message: `Request failed with status ${response.status}`,
    category: "unknown_error",
    statusCode: response.status,
  });
}

async function request<T>(
  path: string,
  init: RequestInit,
  options: RequestOptions = {}
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeoutController = new AbortController();
  const timeoutId = setTimeout(() => timeoutController.abort(), timeoutMs);

  const externalSignal = options.signal;
  const combined = externalSignal
    ? combineSignals([externalSignal, timeoutController.signal])
    : { signal: timeoutController.signal, cleanup: () => undefined };

  const headers = new Headers(init.headers ?? {});
  headers.set("Accept", "application/json");

  if (init.body !== undefined && init.body !== null) {
    headers.set("Content-Type", "application/json");
  }

  // Attach the bearer token from the in-memory auth provider (never stored in
  // localStorage or a public env var) and the selected tenant selector.
  const token = await getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const tenantId = getSelectedTenant();
  if (tenantId && !headers.has(TENANT_HEADER)) {
    headers.set(TENANT_HEADER, tenantId);
  }

  const url = buildApiUrl(path, options.baseUrl ?? getApiBaseUrl());

  try {
    const response = await fetch(url, {
      ...init,
      headers,
      signal: combined.signal,
    });

    if (!response.ok) {
      await handleErrorResponse(response);
    }

    if (response.status === 204) {
      return undefined as T;
    }

    const payload = await parseJsonResponse(response);
    return payload as T;
  } catch (error) {
    if (isAbortError(error)) {
      if (externalSignal?.aborted) {
        throw new SignalForgeApiError({
          message: "Request was cancelled",
          category: "api_error",
          cause: error,
        });
      }
      throw new SignalForgeApiError({
        message: "Request timed out",
        category: "timeout",
        cause: error,
      });
    }

    if (error instanceof SignalForgeApiError) {
      throw error;
    }

    throw new SignalForgeApiError({
      message: "Network request failed",
      category: "network_error",
      cause: error,
    });
  } finally {
    clearTimeout(timeoutId);
    combined.cleanup();
  }
}

export function apiGet<T>(path: string, options?: RequestOptions): Promise<T> {
  return request<T>(path, { method: "GET" }, options);
}

export function apiPostJson<T>(
  path: string,
  body: unknown,
  options?: RequestOptions
): Promise<T> {
  return request<T>(
    path,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
    options
  );
}

export function apiPostNoBody<T>(
  path: string,
  options?: RequestOptions
): Promise<T> {
  return request<T>(path, { method: "POST" }, options);
}

export const apiClient = {
  get: apiGet,
  postJson: apiPostJson,
  postNoBody: apiPostNoBody,
};
