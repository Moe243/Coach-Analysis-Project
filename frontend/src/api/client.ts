import type { ApiPage } from "./contracts";

const configuredBase = import.meta.env.VITE_API_BASE_URL?.trim();
export const API_BASE_URL = (configuredBase || "/api").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const API_WAKE_RETRY_LIMIT = 5;

export function isRetryableApiError(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status === 429 || [502, 503, 504].includes(error.status);
  }
  return error instanceof TypeError;
}

type QueryValue = string | number | boolean | null | undefined;

export function queryString(values: Record<string, QueryValue>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export async function apiGet<T>(
  path: string,
  values: Record<string, QueryValue> = {},
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}${queryString(values)}`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export async function apiGetAll<T>(
  path: string,
  values: Record<string, QueryValue> = {},
  signal?: AbortSignal,
): Promise<T[]> {
  const rows: T[] = [];
  let offset = 0;
  while (true) {
    const page = await apiGet<ApiPage<T>>(
      path,
      { ...values, limit: 200, offset },
      signal,
    );
    rows.push(...page.items);
    offset += page.items.length;
    if (offset >= page.total || page.items.length === 0) return rows;
  }
}
