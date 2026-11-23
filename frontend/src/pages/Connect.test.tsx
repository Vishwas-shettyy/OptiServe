import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ADMIN, EMPTY_STATS, HEALTH, renderApp, stubFetch } from "../test/utils";
import { INSTALL_SCRIPT_URL, installCommand, isLocalAddress } from "./Connect";

const base = {
  "GET /api/auth/me": { body: ADMIN },
  "GET /api/health": { body: HEALTH },
  "GET /api/stats": { body: EMPTY_STATS },
  "GET /api/recommendations": { body: [] },
};

const TOKEN = { id: 5, label: "web-1", created_at: "2026-11-23T12:00:00Z", revoked: false, last_used_at: null, server_name: null };

describe("install command helpers", () => {
  it("builds the one-liner without a trailing slash", () => {
    expect(installCommand("https://ops.example.com/ ", "osa_abc")).toBe(
      `curl -fsSL ${INSTALL_SCRIPT_URL} | sudo bash -s -- https://ops.example.com osa_abc`,
    );
  });

  it("spots addresses a remote server can't reach", () => {
    expect(isLocalAddress("http://localhost:5173")).toBe(true);
    expect(isLocalAddress("http://127.0.0.1:8000")).toBe(true);
    expect(isLocalAddress("https://ops.example.com")).toBe(false);
    expect(isLocalAddress("not a url")).toBe(false);
  });
});

describe("Connect page", () => {
  it("opens automatically from Home when there are no servers", async () => {
    stubFetch(base);
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Connect your first server" })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Connect AWS/ })).toBeTruthy();
  });

  it("agent: token → copyable command → waiting → success when the first metric arrives", async () => {
    let reported = false;
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    stubFetch({
      ...base,
      "POST /api/agent-tokens": (body) => ({
        status: 201,
        body: { ...TOKEN, label: (body as { label: string }).label, token: "osa_secret123" },
      }),
      "GET /api/agent-tokens": () => ({
        body: [reported ? { ...TOKEN, last_used_at: "2026-11-23T12:00:10Z", server_name: "web-1" } : TOKEN],
      }),
    });
    renderApp("/connect");

    fireEvent.click(await screen.findByRole("button", { name: /Install the agent/ }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "web-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create install command" }));

    const command = await screen.findByTestId("install-command");
    expect(command.textContent).toContain("osa_secret123");
    expect(command.textContent).toContain(window.location.origin);
    expect(screen.getByText(/only works on this computer/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(command.textContent));
    expect(await screen.findByRole("button", { name: "Copied" })).toBeTruthy();

    expect(screen.getByText("Waiting for your server…")).toBeTruthy();
    reported = true;
    expect(await screen.findByText("web-1 is connected", undefined, { timeout: 5_000 })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Go to Home" }));
    expect(await screen.findByRole("heading", { name: "Connect your first server" })).toBeTruthy();
  });

  it("aws: test shows what was found, then connect backfills and succeeds", async () => {
    const sent: unknown[] = [];
    stubFetch({
      ...base,
      "POST /api/connections/aws/test": (body) => {
        sent.push(body);
        return {
          body: {
            account_id: "123456789012",
            region: "ap-south-1",
            instances: [
              { instance_id: "i-1", name: "web-a", state: "running", instance_type: "t3.micro", managed: true, group: "optiserve-demo" },
              { instance_id: "i-2", name: "forgotten-test-box", state: "running", instance_type: "t3.micro", managed: true, group: null },
            ],
            groups: [{ name: "optiserve-demo", min_size: 1, max_size: 3, desired: 1, managed: true }],
          },
        };
      },
      "POST /api/connections/aws": (body) => {
        sent.push(body);
        return {
          status: 201,
          body: {
            connection: { id: 1, kind: "aws", name: "AWS 123456789012", region: "ap-south-1", status: "ok", last_sync_at: null, error_message: null },
            sync: { connection_id: 1, instances: 2, groups: 1, points_added: 672, period_s: 3600, backfill: true, impaired: [] },
          },
        };
      },
    });
    renderApp("/connect");
    fireEvent.click(await screen.findByRole("button", { name: /Connect AWS/ }));
    expect(screen.getByText(/IAM role/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Use access keys instead/ }));
    fireEvent.change(screen.getByLabelText("Access key ID"), { target: { value: "AKIAIOSFODNN7EXAMPLE" } });
    fireEvent.change(screen.getByLabelText("Secret access key"), { target: { value: "s".repeat(40) } });
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));

    expect(await screen.findByText("forgotten-test-box")).toBeTruthy();
    expect(screen.getByText("servers found")).toBeTruthy();
    expect(screen.getByText("OptiServe can change it")).toBeTruthy();
    expect(sent[0]).toEqual({ region: "ap-south-1", access_key_id: "AKIAIOSFODNN7EXAMPLE", secret_access_key: "s".repeat(40) });

    fireEvent.click(screen.getByRole("button", { name: "Connect and bring in history" }));
    const done = await screen.findByRole("status");
    await waitFor(() => expect(within(done).getByText("AWS is connected")).toBeTruthy());
    expect(done.textContent).toContain("672 readings");
    expect(screen.getByRole("button", { name: "Go to Home" })).toBeTruthy();
  });

  it("aws: shows the plain reason when the test fails", async () => {
    stubFetch({
      ...base,
      "POST /api/connections/aws/test": { status: 400, body: { detail: "AWS rejected these credentials." } },
    });
    renderApp("/connect");
    fireEvent.click(await screen.findByRole("button", { name: /Connect AWS/ }));
    fireEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect((await screen.findByRole("alert")).textContent).toContain("AWS rejected these credentials.");
    expect(screen.queryByRole("button", { name: "Connect and bring in history" })).toBeNull();
  });
});
