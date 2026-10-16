import type { ApiErrorBody, CamerasResponse, CameraScope, DataHealth, GeocodeResponse, PlanRequest, PlanResponse, RegionResponse } from "./types";

// Same-origin by default: the nginx edge proxies /api/ to the backend, so no CORS and no third party.
const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;
  readonly requestId: string | null;

  constructor(code: string, message: string, status: number, details: Record<string, unknown>, requestId: string | null) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(BASE + path, {
    ...init,
    headers: { Accept: "application/json", ...(init.body ? { "Content-Type": "application/json" } : {}), ...(init.headers ?? {}) },
    cache: "no-store",
  });
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = null;
  }
  if (!response.ok) {
    const envelope = body as ApiErrorBody | null;
    throw new ApiError(
      envelope?.error?.code ?? `HTTP_${response.status}`,
      envelope?.error?.message ?? `Request failed with status ${response.status}.`,
      response.status,
      envelope?.error?.details ?? {},
      envelope?.request_id ?? response.headers.get("x-request-id"),
    );
  }
  return body as T;
}

export const api = {
  region: (signal?: AbortSignal) => request<RegionResponse>("/api/v1/region", { signal }),
  dataHealth: (signal?: AbortSignal) => request<DataHealth>("/api/v1/health/data", { signal }),
  plan: (body: PlanRequest, signal?: AbortSignal) => request<PlanResponse>("/api/v1/routes/plan", { method: "POST", body: JSON.stringify(body), signal }),
  geocode: (query: string, signal?: AbortSignal) => request<GeocodeResponse>("/api/v1/geocode", { method: "POST", body: JSON.stringify({ query, limit: 5 }), signal }),
  cameras: (bboxWsen: [number, number, number, number], scope: CameraScope, signal?: AbortSignal) =>
    request<CamerasResponse>(`/api/v1/cameras?bbox=${encodeURIComponent(bboxWsen.map((v) => v.toFixed(5)).join(","))}&scope=${scope}`, { signal }),
};

export function describeError(error: unknown): { code: string; message: string } {
  if (error instanceof ApiError) {
    return { code: error.code, message: error.message };
  }
  if (error instanceof DOMException && error.name === "AbortError") {
    return { code: "CANCELLED", message: "Request cancelled." };
  }
  if (error instanceof TypeError) {
    return { code: "NETWORK", message: "The server could not be reached." };
  }
  return { code: "UNKNOWN", message: "Something went wrong." };
}
