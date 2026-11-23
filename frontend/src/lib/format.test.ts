import { describe, expect, it } from "vitest";
import { formatInr, formatPct, plural, timeAgo, withZone } from "./format";

describe("formatInr", () => {
  it("uses Indian digit grouping and the rupee sign", () => {
    expect(formatInr(420000)).toBe("₹4,20,000");
    expect(formatInr(4200.4)).toBe("₹4,200");
    expect(formatInr(0)).toBe("₹0");
  });
  it("shows paise for small amounts when precise, and a real minus sign", () => {
    expect(formatInr(8.6, { precise: true })).toBe("₹8.60");
    expect(formatInr(-1500)).toBe("−₹1,500");
    expect(formatInr(Number.NaN)).toBe("₹0");
  });
});

describe("formatPct", () => {
  it("rounds and uses a dash for unknown", () => {
    expect(formatPct(23.4)).toBe("23%");
    expect(formatPct(23.45, 1)).toBe("23.4%");
    expect(formatPct(null)).toBe("—");
  });
});

describe("timeAgo", () => {
  const now = Date.parse("2026-11-23T12:00:00Z");
  it("reads like '3 s ago'", () => {
    expect(timeAgo("2026-11-23T11:59:57Z", now)).toBe("3 s ago");
    expect(timeAgo("2026-11-23T11:59:59.5Z", now)).toBe("just now");
    expect(timeAgo("2026-11-23T11:55:00Z", now)).toBe("5 min ago");
    expect(timeAgo("2026-11-23T09:00:00Z", now)).toBe("3 h ago");
    expect(timeAgo("2026-11-20T12:00:00Z", now)).toBe("3 d ago");
    expect(timeAgo(null, now)).toBe("never");
  });
  it("treats zone-less backend timestamps as UTC", () => {
    expect(withZone("2026-11-23T11:59:57")).toBe("2026-11-23T11:59:57Z");
    expect(timeAgo("2026-11-23T11:59:57", now)).toBe("3 s ago");
    expect(withZone("2026-11-23T11:59:57+00:00")).toBe("2026-11-23T11:59:57+00:00");
  });
});

describe("plural", () => {
  it("says 1 server / 2 servers", () => {
    expect(plural(1, "server")).toBe("1 server");
    expect(plural(2, "server")).toBe("2 servers");
  });
});
