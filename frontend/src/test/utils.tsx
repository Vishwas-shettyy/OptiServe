// Test helpers: render with providers, and a fetch stub that answers by "METHOD /path".
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppRoutes, makeQueryClient } from "../App";
import { ToastProvider } from "../components/Toast";

export type Reply = { status?: number; body: unknown };
export type Routes = Record<string, Reply | ((body: unknown) => Reply)>;

/** Replace global fetch; unknown routes return 404. Returns the mock to inspect calls. */
export function stubFetch(routes: Routes) {
  const mock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const key = `${init?.method ?? "GET"} ${url.pathname}`;
    const route = routes[key];
    const sent: unknown = typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
    const reply: Reply = route === undefined ? { status: 404, body: { detail: "Not found" } } : typeof route === "function" ? route(sent) : route;
    return new Response(JSON.stringify(reply.body), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

export function testClient(): QueryClient {
  return makeQueryClient({ retry: false });
}

export function renderWithProviders(ui: ReactElement, path = "/"): RenderResult {
  return render(
    <QueryClientProvider client={testClient()}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

export function renderApp(path = "/"): RenderResult {
  return renderWithProviders(<AppRoutes />, path);
}

export const ADMIN = { email: "admin@test.local" };
export const HEALTH = { status: "ok", version: "2.0.0", live_mode: true, dry_run: true };
export const EMPTY_STATS = {
  avg_busy_pct: null,
  servers: 0,
  servers_without_price: 0,
  monthly_cost_inr: 0,
  potential_savings_inr: 0,
  realized_savings_inr: 0,
  accuracy_pct: null,
  accuracy_points: 0,
  live_mode: true,
  dry_run: true,
  as_of: "2026-11-23T12:00:00Z",
};
