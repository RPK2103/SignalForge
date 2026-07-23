const DEFAULT_DEV_API_BASE_URL = "http://127.0.0.1:8000";

export function normalizeBaseUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) {
    throw new Error("API base URL is empty");
  }
  return trimmed.replace(/\/+$/, "");
}

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL;

  if (configured && configured.trim()) {
    return normalizeBaseUrl(configured);
  }

  if (process.env.NODE_ENV === "development") {
    return normalizeBaseUrl(DEFAULT_DEV_API_BASE_URL);
  }

  throw new Error(
    "NEXT_PUBLIC_SIGNALFORGE_API_BASE_URL must be set in production"
  );
}

export function buildApiUrl(path: string, baseUrl?: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const root = baseUrl ?? getApiBaseUrl();
  return `${root}${normalizedPath}`;
}
