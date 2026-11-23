import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/utils";
import { ServerIcon } from "../lib/icons";
import { Button } from "./Button";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { Pill } from "./Pill";
import { Skeleton } from "./Skeleton";
import { StatNumber } from "./StatNumber";
import { useToast } from "./Toast";

afterEach(() => {
  vi.useRealTimers();
});

describe("shared components", () => {
  it("StatNumber always puts a word next to the number", () => {
    renderWithProviders(<StatNumber value="23%" label="busy" hint="Across 3 servers" />);
    expect(screen.getByText("23%").nextElementSibling?.textContent).toBe("busy");
    expect(screen.getByText("Across 3 servers")).toBeTruthy();
  });

  it("Card shows its title and content", () => {
    renderWithProviders(<Card title="Copilot">content</Card>);
    expect(screen.getByRole("heading", { name: "Copilot" })).toBeTruthy();
    expect(screen.getByText("content")).toBeTruthy();
  });

  it("Button disables itself while loading", () => {
    const onClick = vi.fn();
    renderWithProviders(
      <Button loading onClick={onClick}>
        Approve
      </Button>,
    );
    const btn = screen.getByRole("button", { name: "Approve" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onClick).not.toHaveBeenCalled();
  });

  it("Pill, Skeleton, EmptyState and ErrorState render their states", () => {
    const retry = vi.fn();
    renderWithProviders(
      <div>
        <Pill tone="accent">Live mode</Pill>
        <Skeleton lines={2} />
        <EmptyState icon={ServerIcon} title="No servers yet">
          Install the agent.
        </EmptyState>
        <ErrorState error={new Error("Can't reach the OptiServe server.")} onRetry={retry} />
      </div>,
    );
    expect(screen.getByText("Live mode")).toBeTruthy();
    expect(screen.getByRole("status", { name: "Loading" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "No servers yet" })).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Can't reach the OptiServe server.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("Toast shows a message and hides it after a few seconds", async () => {
    vi.useFakeTimers();
    function Trigger() {
      const toast = useToast();
      return <button onClick={() => toast.show("Saved", "success")}>go</button>;
    }
    renderWithProviders(<Trigger />);
    fireEvent.click(screen.getByText("go"));
    expect(screen.getByText("Saved")).toBeTruthy();
    act(() => {
      vi.advanceTimersByTime(10_000);
    });
    vi.useRealTimers(); // the exit animation finishes on a real frame
    await waitFor(() => expect(screen.queryByText("Saved")).toBeNull());
  });
});
