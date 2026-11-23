import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { headline } from "./pages/Home";
import { ADMIN, EMPTY_STATS, HEALTH, renderApp, stubFetch } from "./test/utils";

const signedIn = {
  "GET /api/auth/me": { body: ADMIN },
  "GET /api/health": { body: HEALTH },
  "GET /api/stats": { body: EMPTY_STATS },
  "GET /api/recommendations": { body: [] },
  "GET /api/actions": { body: [] },
  "GET /api/connections": { body: [] },
  "GET /api/agent-tokens": { body: [] },
  "GET /api/servers": { body: [] },
  "GET /api/settings": {
    body: { risk: 0.5, live_mode: true, dry_run: true, target_util_pct: 70, updated_at: null, updated_by: null },
  },
};

describe("auth flow", () => {
  it("sends a signed-out visitor to Login, then back to the page they wanted", async () => {
    let signed = false;
    const fetchMock = stubFetch({
      ...signedIn,
      "GET /api/auth/me": () => (signed ? { body: ADMIN } : { status: 401, body: { detail: "Please sign in." } }),
      "POST /api/auth/login": (body) => {
        signed = true;
        return { body: { email: (body as { email: string }).email } };
      },
    });
    renderApp("/activity");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: ADMIN.email } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "pw" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Activity" })).toBeTruthy();
    expect(await screen.findByText("Nothing has changed yet")).toBeTruthy();
    const login = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(login?.[1]?.credentials).toBe("include");
  });

  it("shows the backend's message when the password is wrong", async () => {
    stubFetch({
      "GET /api/auth/me": { status: 401, body: { detail: "Please sign in." } },
      "POST /api/auth/login": { status: 401, body: { detail: "Wrong email or password." } },
    });
    renderApp("/");
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "a@b.c" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Wrong email or password.");
  });
});

describe("pages and layout", () => {
  it("Home with no servers tells you how to connect, and the top bar shows the live-mode badge", async () => {
    stubFetch(signedIn);
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Connect your first server" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Install the agent/ })).toBeTruthy();
    expect(await screen.findByText("Live mode")).toBeTruthy();
    for (const name of ["Home", "Servers", "Activity", "Settings"]) {
      expect(screen.getAllByRole("link", { name }).length).toBeGreaterThan(0);
    }
  });

  it.each([
    ["/servers", "No servers yet"],
    ["/servers/7", "No details for this server yet"],
    ["/activity", "Nothing has changed yet"],
    ["/connect", "Connect your first server"],
    ["/nowhere", "This page doesn't exist"],
  ])("%s shows a clean empty state", async (path, text) => {
    stubFetch(signedIn);
    renderApp(path);
    expect(await screen.findByText(text)).toBeTruthy();
  });

  it("Settings shows empty connections and tokens", async () => {
    stubFetch(signedIn);
    renderApp("/settings");
    expect(await screen.findByText("Nothing connected")).toBeTruthy();
    expect(await screen.findByText("No agent tokens")).toBeTruthy();
    expect(await screen.findByText(/^Dry run is on\./)).toBeTruthy();
  });

  it("Home with servers leads with one plain headline", async () => {
    const stats = { ...EMPTY_STATS, servers: 3, avg_busy_pct: 23.2, potential_savings_inr: 4200 };
    stubFetch({ ...signedIn, "GET /api/stats": { body: stats } });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Your servers are 23% busy. You can save ₹4,200/month." })).toBeTruthy();
    await waitFor(() => expect(screen.getByText("Nothing to change right now")).toBeTruthy());
  });

  it("a 401 from any page signs the user out", async () => {
    let meCalls = 0;
    stubFetch({
      ...signedIn,
      "GET /api/auth/me": () => (meCalls++ === 0 ? { body: ADMIN } : { status: 401, body: {} }),
      "GET /api/stats": { status: 401, body: { detail: "Your session has ended. Please sign in again." } },
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Sign in" })).toBeTruthy();
  });
});

describe("headline", () => {
  it("is honest when there are no numbers yet or nothing to save", () => {
    expect(headline({ ...EMPTY_STATS, servers: 1 })).toMatch(/waiting for their first numbers/);
    expect(headline({ ...EMPTY_STATS, servers: 1, avg_busy_pct: 41 })).toBe("Your servers are 41% busy. Nothing to change right now.");
  });
});
