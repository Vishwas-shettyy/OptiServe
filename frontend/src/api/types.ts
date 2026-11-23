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

export type FleetStatus = "busy" | "normal" | "idle" | "unhealthy" | "stopped";

/** One live-fleet tile. */
export interface FleetServer {
  id: number;
  name: string;
  provider: ConnectionKind;
  instance_type: string | null;
  state: "running" | "stopped" | "unknown";
  status: FleetStatus;
  cpu_pct: number | null;
  mem_pct: number | null;
  /** null when the price is not known (or the server is stopped). */
  monthly_cost_inr: number | null;
  reason: string;
  last_seen_at: string | null;
}

export interface FleetGroup {
  id: number;
  name: string;
  provider: ConnectionKind;
  managed: boolean;
  min_size: number;
  max_size: number;
  desired: number;
  servers: FleetServer[];
}

export type WeatherKind = "sun" | "cloud" | "storm";

export interface WeatherSlot {
  start: string;
  kind: WeatherKind;
  /** Expected share of the running servers' capacity (0..1+). */
  expected_util: number;
  high_util: number;
}

export interface Weather {
  horizon: "60 min" | "24 h";
  live_mode: boolean;
  status: "ok" | "learning" | "no_data";
  message: string;
  capacity: number;
  slots: WeatherSlot[];
  as_of: string;
}

/** A row on the Servers page (a fleet tile plus its group and price details). */
export interface ServerRow extends FleetServer {
  group_id: number | null;
  group_name: string;
  managed: boolean;
  /** USD per hour in use; null when unknown. */
  hourly_usd: number | null;
  price_source: "override" | "table" | null;
  table_hourly_usd: number | null;
}

/** One minute on the detail chart, in servers' worth of work (1 = one server fully busy). */
export interface ChartPoint {
  ts: string;
  load: number | null;
  server: number | null;
  expected: number | null;
  low: number | null;
  high: number | null;
}

export interface SafetyCheck {
  number: number;
  rule: string;
  status: "pass" | "adjusted" | "blocked";
  message: string;
}

export interface ServerDetail {
  server: ServerRow;
  capacity: number;
  target_util_pct: number;
  chart: ChartPoint[];
  sees: string[];
  safety: SafetyCheck[];
  recommendation: Recommendation | null;
  as_of: string;
}

export interface AppSettings {
  /** 0 = save more … 1 = stay safe. */
  risk: number;
  live_mode: boolean;
  dry_run: boolean;
  target_util_pct: number;
  updated_at: string | null;
  updated_by: string | null;
}

export type AppSettingsUpdate = Partial<Pick<AppSettings, "risk" | "live_mode" | "dry_run">>;

export interface RemoveResult {
  removed_connection_id: number;
  servers_removed: number;
}

export interface ActionChart {
  action_id: number;
  changed_at: string | null;
  before_servers: number | null;
  after_servers: number | null;
  points: { ts: string; load: number }[];
}
