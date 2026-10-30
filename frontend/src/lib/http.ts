/** HTTP client wrapper with unified error parsing. */

import type { ApiErrorDetail } from "@/types/api";

export class HttpClientError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly detail?: unknown;

  constructor(code: string, message: string, status: number, detail?: unknown) {
    super(message);
    this.name = "HttpClientError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

function isErrorPayload(data: unknown): data is { error: ApiErrorDetail } {
  return (
    typeof data === "object" &&
    data !== null &&
    "error" in data &&
    typeof (data as { error: unknown }).error === "object" &&
    (data as { error: unknown }).error !== null
  );
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, {
    ...options,
    headers,
  });

  if (response.status === 204) {
    return undefined as unknown as T;
  }

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const payload: unknown = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    if (isErrorPayload(payload)) {
      throw new HttpClientError(
        payload.error.code || "API_ERROR",
        payload.error.message || `请求失败 (${response.status})`,
        response.status,
        payload.error.detail
      );
    }
    throw new HttpClientError(
      "HTTP_ERROR",
      typeof payload === "string" && payload ? payload : `请求失败 (${response.status})`,
      response.status
    );
  }

  return payload as T;
}
