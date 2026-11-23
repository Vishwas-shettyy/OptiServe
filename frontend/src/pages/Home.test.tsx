import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { FleetGroup, FleetServer, Recommendation, Weather } from "../api/types";
import { weatherSummary } from "../components/CapacityWeather";
import { impactText, progressStep } from "../components/CopilotFeed";
import { breathSeconds, loadOf, tileLabel } from "../components/LiveFleet";
import { ADMIN, EMPTY_STATS, HEALTH, renderApp, stubFetch } from "../test/utils";

const STATS = { ...EMPTY_STATS, avg_busy_pct: 23, servers: 4, potential_savings_inr: 4200, realized_savings_inr: 1530 };

function server(over: Partial<FleetServer>): FleetServer {
  return {
    id: 1,
    name: "web-1",
    provider: "aws",
    instance_type: "t3.micro",
    state: "running",
    status: "normal",
    cpu_pct: 30,
    mem_pct: null,
    monthly_cost_inr: 630,
    reason: "Running normally at 30% busy.",
    last_seen_at: "2026-11-23T12:00:00Z",
    ...over,
  };
}

const GROUPS: FleetGroup[] = [
  {
    id: 1,
    name: "optiserve-demo",
    provider: "aws",
    managed: true,
    min_size: 1,
    max_size: 3,
    desired: 2,
    servers: [
      server({ id: 1, name: "web-1", cpu_pct: 91, status: "busy" }),
      server({ id: 2, name: "web-2", cpu_pct: 20 }),
      server({ id: 3, name: "forgotten-test-box", cpu_pct: 1, status: "idle", reason: "Almost no work for 10 minutes." }),
      server({ id: 4, name: "db-1", status: "unhealthy", reason: "This server has sent no data for 5 minutes." }),
    ],
  },
];

const slot = (h: number, kind: "sun" | "cloud" | "storm") => ({
  start: `2026-11-23T${String(h).padStart(2, "0")}:00:00Z`,
  kind,
  expected_util: 0.5,
  high_util: 0.6,
});

const WEATHER: Weather = {
  horizon: "24 h",
  live_mode: false,
  status: "ok",
  message: "",
  capacity: 3,
  slots: [slot(12, "sun"), slot(14, "cloud"), slot(16, "storm"), slot(18, "cloud")],
  as_of: "2026-11-23T12:00:00Z",
};

function rec(over: Partial<Recommendation>): Recommendation {
  return {
    id: 9,
    group_id: 1,
    group_name: "optiserve-demo",
    server_id: 3,
    server_name: "forgotten-test-box",
    kind: "stop_idle",
    from_count: 1,
    to_count: 0,
    reason: "forgotten-test-box has been idle for 10 minutes. Stop it to save money.",
    savings_month_inr: 630,
    confidence: 0.9,
    status: "pending",
    blocked_reason: null,
    created_at: "2026-11-23T12:00:00Z",
    expires_at: null,
    can_execute: true,
    recommendation_only_reason: null,
    ...over,
  };
}

const base = {
  "GET /api/auth/me": { body: ADMIN },
  "GET /api/health": { body: HEALTH },
  "GET /api/stats": { body: STATS },
  "GET /api/groups": { body: GROUPS },
  "GET /api/forecast/weather": { body: WEATHER },
  "GET /api/recommendations": { body: [] },
  "GET /api/actions": { body: [] },
};

describe("Home helpers", () => {
  it("colours and breathing follow CPU", () => {
    expect([loadOf(null), loadOf(49), loadOf(50), loadOf(79), loadOf(80)]).toEqual(["calm", "calm", "warm", "warm", "hot"]);
    expect(breathSeconds(0)).toBe(4.5);
    expect(breathSeconds(100)).toBe(1.2);
    expect(breathSeconds(250)).toBe(1.2);
    expect(tileLabel(server({ cpu_pct: 91 }))).toBe("web-1: 91% busy, very busy");
    expect(tileLabel(server({ status: "idle" }))).toContain("asleep");
  });

  it("summarises the weather in one line", () => {
    const clock = (iso: string) => iso.slice(11, 16);
    expect(weatherSummary(WEATHER, clock)).toBe("Storm expected at 16:00.");
    expect(weatherSummary({ ...WEATHER, slots: [slot(12, "storm")] }, clock)).toContain("Storm now");
    expect(weatherSummary({ ...WEATHER, slots: [slot(12, "sun")] }, clock)).toBe("Quiet ahead: no storms in the next 24 h.");
    expect(weatherSummary({ ...WEATHER, horizon: "60 min", slots: [slot(12, "cloud")] }, clock)).toBe(
      "Normal load ahead: no storms in the next 60 min.",
    );
  });

  it("maps statuses to progress steps and impact words", () => {
    expect(["pending", "approved", "executing", "done", "failed"].map((s) => progressStep(s as never))).toEqual([null, 0, 1, 2, 2]);
    expect(impactText(rec({}))).toBe("Saves ₹630/month");
    expect(impactText(rec({ kind: "scale_up", savings_month_inr: 0 }))).toBe("Avoids running out of room");
    expect(impactText(rec({ kind: "hold", savings_month_inr: 0 }))).toBeNull();
  });
});

describe("Home", () => {
  it("shows the headline, savings counter, live fleet and weather", async () => {
    stubFetch(base);
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Your servers are 23% busy. You can save ₹4,200/month." })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("savings-counter").textContent).toBe("₹1,530"));
    expect(screen.getByText("saved so far")).toBeTruthy();

    const busy = await screen.findByRole("link", { name: "web-1: 91% busy, very busy" });
    expect(busy.getAttribute("href")).toBe("/servers/1");
    expect(busy.querySelector(".breathe")).toBeTruthy();
    const asleep = screen.getByRole("link", { name: /forgotten-test-box: asleep/ });
    expect(asleep.textContent).toContain("zZ");
    expect(asleep.querySelector(".breathe")).toBeNull();
    expect(screen.getByRole("link", { name: /db-1: needs attention/ }).getAttribute("data-status")).toBe("unhealthy");
    expect(screen.getByText("OptiServe can change it")).toBeTruthy();

    expect(await screen.findByText(/^Storm expected at /)).toBeTruthy();
    expect(screen.getByText("Capacity weather · next 24 h")).toBeTruthy();
    expect(document.querySelectorAll("[data-kind]").length).toBe(4);
    expect(await screen.findByText("Nothing to change right now")).toBeTruthy();
  });

  it("approving shows progress through to Done", async () => {
    let approved = false;
    stubFetch({
      ...base,
      "GET /api/recommendations": () => ({ body: [rec(approved ? { status: "done" } : {})] }),
      "POST /api/recommendations/9/approve": () => {
        approved = true;
        return { body: { recommendation: rec({ status: "approved" }), action: {} } };
      },
      "GET /api/actions": () => ({
        body: approved ? [{ id: 1, recommendation_id: 9, result: "dry_run", status: "done" }] : [],
      }),
    });
    renderApp("/");
    const card = (await screen.findByText("Stop forgotten-test-box")).closest("article") as HTMLElement;
    expect(within(card).getByText("Saves ₹630/month")).toBeTruthy();
    fireEvent.click(within(card).getByRole("button", { name: "Approve" }));

    const progress = await within(card).findByRole("status");
    await waitFor(() => expect(within(progress).getByText("Done")).toBeTruthy());
    expect(within(progress).getByText("Approved")).toBeTruthy();
    expect(within(progress).getByText("Changing…")).toBeTruthy();
    expect(await within(card).findByText(/Practice run/)).toBeTruthy();
    expect(within(card).queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("blocked cards show the reason and no Approve button", async () => {
    stubFetch({
      ...base,
      "GET /api/recommendations": {
        body: [rec({ status: "blocked", blocked_reason: "A server in this group is unhealthy, so nothing is removed." })],
      },
    });
    renderApp("/");
    expect(await screen.findByText("On hold")).toBeTruthy();
    expect(screen.getByText("A server in this group is unhealthy, so nothing is removed.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("each part has its own error and learning states", async () => {
    stubFetch({
      ...base,
      "GET /api/groups": { status: 500, body: {} },
      "GET /api/forecast/weather": {
        body: { ...WEATHER, status: "no_data", slots: [], message: "OptiServe needs about 15 minutes of numbers before it can forecast." },
      },
    });
    renderApp("/");
    expect(await screen.findByText("OptiServe needs about 15 minutes of numbers before it can forecast.")).toBeTruthy();
    expect(await screen.findByText("The OptiServe server had a problem. Try again in a moment.")).toBeTruthy();
  });
});
