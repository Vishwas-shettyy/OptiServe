// Typed fetch client for every backend route used by the UI. Same-origin /api (Vite proxies it to the backend).
import type {
  Action,
  AgentToken,
  AgentTokenCreated,
  ApproveResponse,
  AwsConnectBody,
  AwsConnectResponse,
  Connection,
  Health,
  LoginBody,
  Ok,
  Recommendation,
  RecommendationStatus,
  Stats,
  SyncResult,
  User,
} from "./types";

/** An HTTP error with the backend's plain-words message. */
export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Method = "GET" | "POST" | "DELETE";

function messageFrom(status: number, body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first: unknown = detail[0];
      if (first && typeof first === "object" && "msg" in first && typeof first.msg === "string") {
        return first.msg.replace(/^Value error, /, "");
      }
    }
  }
  if (status === 401) return "Please sign in.";
  if (status >= 500) return "The OptiServe server had a problem. Try again in a moment.";
  return `Request failed (${status}).`;
}

/** Call the API; throws ApiError with a readable message on failure. */
export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      method,
      credentials: "include",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach the OptiServe server. Check that the backend is running.");
  }
  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!res.ok) throw new ApiError(res.status, messageFrom(res.status, data));
  return data as T;
}

function query(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined) q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),

  login: (body: LoginBody) => request<User>("POST", "/api/auth/login", body),
  logout: () => request<Ok>("POST", "/api/auth/logout"),
  me: () => request<User>("GET", "/api/auth/me"),

  agentTokens: () => request<AgentToken[]>("GET", "/api/agent-tokens"),
  createAgentToken: (label: string) => request<AgentTokenCreated>("POST", "/api/agent-tokens", { label }),
  revokeAgentToken: (id: number) => request<AgentToken>("DELETE", `/api/agent-tokens/${id}`),

  connections: () => request<Connection[]>("GET", "/api/connections"),
  connectAws: (body: AwsConnectBody) => request<AwsConnectResponse>("POST", "/api/connections/aws", body),
  syncConnection: (id: number) => request<SyncResult>("POST", `/api/connections/${id}/sync`),

  recommendations: (statuses?: RecommendationStatus[] | "all", limit?: number) =>
    request<Recommendation[]>(
      "GET",
      `/api/recommendations${query({ status: statuses === "all" ? "all" : statuses?.join(","), limit })}`,
    ),
  approve: (id: number) => request<ApproveResponse>("POST", `/api/recommendations/${id}/approve`),
  reject: (id: number) => request<Recommendation>("POST", `/api/recommendations/${id}/reject`),

  actions: (limit?: number) => request<Action[]>("GET", `/api/actions${query({ limit })}`),
  stats: () => request<Stats>("GET", "/api/stats"),
};
