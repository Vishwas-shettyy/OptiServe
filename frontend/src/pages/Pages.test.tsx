import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Action, Recommendation, ServerDetail, ServerRow } from "../api/types";
import { toPlot } from "../components/LoadChart";
import { ADMIN, EMPTY_STATS, HEALTH, renderApp, stubFetch } from "../test/utils";
import { describeAction, outcome } from "./Activity";
import { filterServers } from "./Servers";
import { riskSentence, targetPct } from "./Settings";

function row(over: Partial<ServerRow>): ServerRow {
  return {
    id: 1,
    name: "web-1",
    provider: "aws",
    instance_type: "t3.micro",
    state: "running",
    status: "normal",
    cpu_pct: 40,
    mem_pct: null,
    monthly_cost_inr: 630,
    reason: "Running normally at 40% busy.",
    last_seen_at: "2026-11-23T12:00:00Z",
    group_id: 1,
    group_name: "optiserve-demo",
    managed: true,
    hourly_usd: 0.0104,
    price_source: "table",
    table_hourly_usd: 0.0104,
    ...over,
  };
}

const ROWS: ServerRow[] = [
  row({ id: 1, name: "web-1", cpu_pct: 88, status: "busy" }),
  row({ id: 2, name: "web-2" }),
  row({ id: 3, name: "forgotten-test-box", status: "idle", cpu_pct: 1, group_name: "Ungrouped", managed: false }),
  row({ id: 4, name: "db-1", status: "unhealthy", instance_type: "m5.large", monthly_cost_inr: null, price_source: null, hourly_usd: null, table_hourly_usd: null }),
];

const SETTINGS = { risk: 0.5, live_mode: false, dry_run: true, target_util_pct: 70, updated_at: null, updated_by: null };

const base = {
  "GET /api/auth/me": { body: ADMIN },
  "GET /api/health": { body: HEALTH },
  "GET /api/stats": { body: { ...EMPTY_STATS, servers: 4, realized_savings_inr: 312.5, accuracy_pct: 91.2, accuracy_points: 1200 } },
  "GET /api/servers": { body: ROWS },
  "GET /api/settings": { body: SETTINGS },
  "GET /api/connections": { body: [] },
  "GET /api/agent-tokens": { body: [] },
  "GET /api/actions": { body: [] },
  "GET /api/recommendations": { body: [] },
};

const REC: Recommendation = {
  id: 9,
  group_id: 1,
  group_name: "optiserve-demo",
  server_id: null,
  server_name: null,
  kind: "scale_up",
  from_count: 1,
  to_count: 2,
  reason: "CPU will reach 88% in about 6 minutes. Add 1 server now so it's ready in time.",
  savings_month_inr: 0,
  confidence: 0.8,
  status: "pending",
  blocked_reason: null,
  created_at: "2026-11-23T12:00:00Z",
  expires_at: null,
  can_execute: true,
  recommendation_only_reason: null,
};

const DETAIL: ServerDetail = {
  server: ROWS[0] as ServerRow,
  capacity: 1,
  target_util_pct: 70,
  chart: [
    { ts: "2026-11-23T11:59:00Z", load: 0.8, server: 0.8, expected: null, low: null, high: null },
    { ts: "2026-11-23T12:01:00Z", load: null, server: null, expected: 0.9, low: 0.7, high: 1.1 },
  ],
  sees: ["Working hard: 88% busy.", "AWS doesn't report memory. Install the agent on this server to see it."],
  safety: [
    { number: 1, rule: "Minimum servers", status: "pass", message: "Keeps at least 1 server running." },
    { number: 6, rule: "Health", status: "blocked", message: "db-1 is unhealthy. Fix it before removing servers." },
  ],
  recommendation: REC,
  as_of: "2026-11-23T12:00:00Z",
};

const ACTION: Action = {
  id: 3,
  recommendation_id: 9,
  group_id: 1,
  group_name: "optiserve-demo",
  kind: "scale_down",
  from_count: 2,
  to_count: 1,
  status: "done",
  approved_by: "admin@test.local",
  approved_at: "2026-11-23T10:00:00Z",
  executed_at: "2026-11-23T10:00:05Z",
  finished_at: "2026-11-23T10:02:00Z",
  result: "done",
  details: { message: "Desired capacity changed from 2 to 1." },
  realized_savings_inr: 42.5,
};

describe("page helpers", () => {
  it("filters servers by text and status", () => {
    expect(filterServers(ROWS, "", "busy").map((r) => r.name)).toEqual(["web-1"]);
    expect(filterServers(ROWS, "UNGROUPED", "all").map((r) => r.name)).toEqual(["forgotten-test-box"]);
    expect(filterServers(ROWS, "m5", "unhealthy").map((r) => r.name)).toEqual(["db-1"]);
    expect(filterServers(ROWS, "web", "idle")).toEqual([]);
  });

  it("explains the risk setting in one line, matching the backend's scale", () => {
    expect([targetPct(0), targetPct(0.5), targetPct(1)]).toEqual([85, 70, 55]);
    expect(riskSentence(0)).toMatch(/^Servers run up to 85% busy: fewer servers/);
    expect(riskSentence(1)).toMatch(/plenty of spare room/);
  });

  it("turns chart rows into plot points with a band", () => {
    const [past, future] = toPlot(DETAIL.chart);
    if (!past || !future) throw new Error("expected two points");
    expect(past.band).toBeNull();
    expect(future.band).toEqual([0.7, 1.1]);
    expect(future.t - past.t).toBe(120_000);
  });

  it("describes actions and their results", () => {
    expect(describeAction(ACTION)).toBe("Remove 1 server from optiserve-demo");
    expect(outcome({ ...ACTION, result: "dry_run" }).label).toBe("Dry run: nothing changed");
    expect(outcome({ ...ACTION, result: null, status: "blocked" }).label).toBe("Stopped by safety check");
  });
});

describe("Servers", () => {
  it("lists servers with busy %, cost, status and managed badge; search and filters narrow it", async () => {
    stubFetch(base);
    renderApp("/servers");
    const table = await screen.findByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(5);
    expect(within(table).getByText("88%")).toBeTruthy();
    expect(within(table).getAllByText("₹630").length).toBe(3);
    expect(within(table).getByText("Price not set")).toBeTruthy();
    expect(within(table).getByText("Unhealthy")).toBeTruthy();
    expect(within(table).getByText("Suggestions only")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Idle/ }));
    await waitFor(() => expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2));
    fireEvent.click(screen.getByRole("button", { name: /^All/ }));
    fireEvent.change(screen.getByLabelText("Search servers"), { target: { value: "zzz" } });
    expect(await screen.findByText(/No servers match/)).toBeTruthy();
  });
});

describe("Server detail", () => {
  it("shows the chart, what OptiServe sees, safety checks and the suggestion with Approve", async () => {
    let approved = false;
    stubFetch({
      ...base,
      "GET /api/servers/1": () => ({
        body: { ...DETAIL, recommendation: approved ? { ...REC, status: "executing" } : REC },
      }),
      "POST /api/recommendations/9/approve": () => {
        approved = true;
        return { body: { recommendation: { ...REC, status: "approved" }, action: ACTION } };
      },
    });
    renderApp("/servers/1");
    expect(await screen.findByRole("heading", { name: "web-1" })).toBeTruthy();
    expect(screen.getByRole("img", { name: /Capacity is 1 servers/ })).toBeTruthy();
    expect(screen.getByText("AWS doesn't report memory. Install the agent on this server to see it.")).toBeTruthy();
    expect(screen.getByText("Health").closest("li")?.getAttribute("data-status")).toBe("blocked");
    expect(screen.getByText("Needs the agent")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Changing…")).toBeTruthy();
  });

  it("an unknown server shows a clean empty state", async () => {
    stubFetch(base);
    renderApp("/servers/77");
    expect(await screen.findByText("No details for this server yet")).toBeTruthy();
  });
});

describe("Activity", () => {
  it("shows savings, accuracy and a timeline entry with who, when, result and a mini-chart", async () => {
    stubFetch({
      ...base,
      "GET /api/actions": { body: [ACTION] },
      "GET /api/actions/3/chart": {
        body: {
          action_id: 3,
          changed_at: "2026-11-23T10:00:05Z",
          before_servers: 2,
          after_servers: 1,
          points: [
            { ts: "2026-11-23T09:50:00Z", load: 0.6 },
            { ts: "2026-11-23T10:10:00Z", load: 0.55 },
          ],
        },
      },
    });
    renderApp("/activity");
    expect(await screen.findByText("Remove 1 server from optiserve-demo")).toBeTruthy();
    expect(screen.getByText(/Approved by admin@test.local/)).toBeTruthy();
    expect(screen.getByText("Done")).toBeTruthy();
    expect(screen.getByText("₹42.50 saved so far")).toBeTruthy();
    expect(await screen.findByText("₹313")).toBeTruthy();
    expect(screen.getByText("91%")).toBeTruthy();
    expect(await screen.findByRole("img", { name: /2 to 1 servers/ })).toBeTruthy();
  });
});

describe("Settings", () => {
  it("risk slider saves, dry run needs confirmation to turn off, prices save", async () => {
    const sent: unknown[] = [];
    let settings = SETTINGS;
    stubFetch({
      ...base,
      "PUT /api/settings": (body) => {
        sent.push(body);
        settings = { ...settings, ...(body as object) };
        return { body: settings };
      },
      "GET /api/settings": () => ({ body: settings }),
      "PUT /api/servers/4/price": (body) => {
        sent.push(body);
        return { body: ROWS[3] as ServerRow };
      },
      "GET /api/connections": {
        body: [{ id: 1, kind: "aws", name: "AWS 1234", region: "ap-south-1", status: "ok", last_sync_at: null, error_message: null }],
      },
      "DELETE /api/connections/1": { body: { removed_connection_id: 1, servers_removed: 2 } },
    });
    renderApp("/settings");

    const slider = await screen.findByLabelText("How careful should OptiServe be?");
    fireEvent.change(slider, { target: { value: "1" } });
    expect(screen.getByText(/Servers run up to 55% busy/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save change" }));
    await waitFor(() => expect(sent).toContainEqual({ risk: 1 }));

    fireEvent.click(screen.getByRole("switch", { name: "Dry run (practice)" }));
    expect(screen.getByRole("alertdialog", { name: "Turn off dry run?" })).toBeTruthy();
    expect(sent).not.toContainEqual({ dry_run: false });
    fireEvent.click(screen.getByRole("button", { name: "Yes, make real changes" }));
    await waitFor(() => expect(sent).toContainEqual({ dry_run: false }));
    expect(await screen.findByText("Approved changes are real. Each one is logged in Activity.")).toBeTruthy();

    fireEvent.click(screen.getByRole("switch", { name: "Live mode" }));
    await waitFor(() => expect(sent).toContainEqual({ live_mode: true }));
    expect(await screen.findByText(/For demos: suggestions come within minutes/)).toBeTruthy();

    const price = screen.getByLabelText("Price per hour for db-1 in US dollars");
    fireEvent.change(price, { target: { value: "0.096" } });
    fireEvent.click(within(price.closest("form") as HTMLElement).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(sent).toContainEqual({ hourly_usd: 0.096 }));

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove" }));
    expect(await screen.findByText(/2 servers no longer shown/)).toBeTruthy();
  });
});
