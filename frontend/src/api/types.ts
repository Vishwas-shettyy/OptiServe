// Response and request shapes, mirroring the backend's pydantic models. Datetimes arrive as ISO strings (UTC).

export interface Health {
  status: string;
  version: string;
  live_mode: boolean;
  dry_run: boolean;
}

export interface User {
  email: string;
}

export interface LoginBody {
  email: string;
  password: string;
}

export interface Ok {
  ok: boolean;
}

export interface AgentToken {
  id: number;
  label: string;
  created_at: string;
  revoked: boolean;
  /** When an agent using this token last sent numbers; null until the first one arrives. */
  last_used_at: string | null;
  /** The server that last reported with this token. */
  server_name: string | null;
}

/** A new token: the secret is shown exactly once. */
export interface AgentTokenCreated extends AgentToken {
  token: string;
}

export type ConnectionKind = "agent" | "aws";

export interface Connection {
  id: number;
  kind: ConnectionKind;
  name: string;
  region: string | null;
  status: "ok" | "error";
  last_sync_at: string | null;
  error_message: string | null;
}

export interface AwsConnectBody {
  region: string;
  access_key_id?: string;
  secret_access_key?: string;
  session_token?: string;
}

export interface SyncResult {
  connection_id: number;
  instances: number;
  groups: number;
  points_added: number;
  period_s: number;
  backfill: boolean;
  impaired: string[];
}

export interface FoundInstance {
  instance_id: string;
  name: string;
  state: string;
  instance_type: string;
  managed: boolean;
  group: string | null;
}

export interface FoundGroup {
  name: string;
  min_size: number;
  max_size: number;
  desired: number;
  managed: boolean;
}

/** What a connection test found. Nothing is saved by a test. */
export interface AwsTestResponse {
  account_id: string;
  region: string;
  instances: FoundInstance[];
  groups: FoundGroup[];
}

export interface AwsConnectResponse {
  connection: Connection;
  sync: SyncResult | null;
}

export type RecommendationKind = "scale_up" | "scale_down" | "stop_idle" | "hold";

export type RecommendationStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "blocked"
  | "executing"
  | "done"
  | "failed"
  | "expired";

export interface Recommendation {
  id: number;
  group_id: number;
  group_name: string;
  server_id: number | null;
  server_name: string | null;
  kind: RecommendationKind;
  from_count: number;
  to_count: number;
  reason: string;
  savings_month_inr: number;
  confidence: number;
  status: RecommendationStatus;
  blocked_reason: string | null;
  created_at: string;
  expires_at: string | null;
  can_execute: boolean;
  recommendation_only_reason: string | null;
}

export type ActionResult = "done" | "failed" | "dry_run";

export interface Action {
  id: number;
  recommendation_id: number;
  group_id: number | null;
  group_name: string | null;
  kind: RecommendationKind | null;
  from_count: number | null;
  to_count: number | null;
  status: RecommendationStatus | null;
  approved_by: string;
  approved_at: string;
  executed_at: string | null;
  finished_at: string | null;
  result: ActionResult | null;
  details: Record<string, unknown>;
  realized_savings_inr: number;
}

export interface ApproveResponse {
  recommendation: Recommendation;
  action: Action;
}

export interface Stats {
  avg_busy_pct: number | null;
  servers: number;
  servers_without_price: number;
  monthly_cost_inr: number;
  potential_savings_inr: number;
  realized_savings_inr: number;
  accuracy_pct: number | null;
  accuracy_points: number;
  live_mode: boolean;
  dry_run: boolean;
  as_of: string;
}
