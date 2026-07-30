export type ApiErrorCategory =
  | "network_error"
  | "timeout"
  | "api_error"
  | "validation_error"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "unsupported_media_type"
  | "database_unavailable"
  | "snapshot_integrity_error"
  | "unknown_error";

export type APIErrorResponse = {
  detail: string | ValidationErrorDetail[];
  status_code: number;
  error_type: string;
};

export type ValidationErrorDetail = {
  type?: string;
  loc?: (string | number)[];
  msg?: string;
  input?: unknown;
};

export class SignalForgeApiError extends Error {
  readonly category: ApiErrorCategory;
  readonly statusCode: number | null;
  readonly errorType: string | null;
  readonly detail: string | ValidationErrorDetail[];

  constructor(options: {
    message: string;
    category: ApiErrorCategory;
    statusCode?: number | null;
    errorType?: string | null;
    detail?: string | ValidationErrorDetail[];
    cause?: unknown;
  }) {
    super(options.message, { cause: options.cause });
    this.name = "SignalForgeApiError";
    this.category = options.category;
    this.statusCode = options.statusCode ?? null;
    this.errorType = options.errorType ?? null;
    this.detail = options.detail ?? options.message;
  }
}

export function isAbortError(error: unknown): boolean {
  return (
    error instanceof DOMException && error.name === "AbortError"
  );
}

export function categorizeErrorType(errorType: string, statusCode: number): ApiErrorCategory {
  switch (errorType) {
    case "validation_error":
      return "validation_error";
    case "record_not_found":
      return "not_found";
    case "persistence_conflict":
      return "conflict";
    case "unsupported_media_type":
      return "unsupported_media_type";
    case "database_unavailable":
      return "database_unavailable";
    case "snapshot_integrity_error":
      return "snapshot_integrity_error";
    case "authentication_failed":
      return "unauthorized";
    case "authorization_denied":
      return "forbidden";
    default:
      if (statusCode === 401) return "unauthorized";
      if (statusCode === 403) return "forbidden";
      if (statusCode === 404) return "not_found";
      if (statusCode === 409) return "conflict";
      if (statusCode === 415) return "unsupported_media_type";
      if (statusCode === 422) return "validation_error";
      if (statusCode === 503) return "database_unavailable";
      return "api_error";
  }
}

export function formatApiErrorMessage(error: SignalForgeApiError): string {
  if (typeof error.detail === "string" && error.detail.trim()) {
    return error.detail;
  }

  if (Array.isArray(error.detail) && error.detail.length > 0) {
    const messages = error.detail
      .map((item) => item.msg)
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  switch (error.category) {
    case "network_error":
      return "Unable to reach the SignalForge API. Check that the backend is running.";
    case "timeout":
      return "The request timed out. Please try again.";
    case "database_unavailable":
      return "Persistence is temporarily unavailable. Run migrations and retry.";
    case "snapshot_integrity_error":
      return "Stored snapshot integrity check failed. Contact an administrator.";
    case "unauthorized":
      return "Your session has expired or you are signed out. Please sign in again.";
    case "forbidden":
      return "You do not have permission to perform this action.";
    case "not_found":
      return "The requested record was not found.";
    case "conflict":
      return "The request conflicted with existing data.";
    case "unsupported_media_type":
      return "Unsupported request format.";
    case "validation_error":
      return "Validation failed. Review the form and try again.";
    default:
      return "An unexpected error occurred.";
  }
}

export function parseApiErrorPayload(payload: unknown): APIErrorResponse | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }

  const candidate = payload as Partial<APIErrorResponse>;
  if (
    typeof candidate.status_code === "number" &&
    typeof candidate.error_type === "string" &&
    (typeof candidate.detail === "string" || Array.isArray(candidate.detail))
  ) {
    return {
      detail: candidate.detail,
      status_code: candidate.status_code,
      error_type: candidate.error_type,
    };
  }

  return null;
}
