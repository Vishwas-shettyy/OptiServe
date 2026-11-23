// Plain-language formatting: ₹ with Indian digit grouping, percentages, "3 s ago".

const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** ₹4,20,000 — whole rupees, or paise for amounts under ₹100 when `precise`. */
export function formatInr(amount: number, { precise = false }: { precise?: boolean } = {}): string {
  if (!Number.isFinite(amount)) return "₹0";
  const sign = amount < 0 ? "−" : "";
  const abs = Math.abs(amount);
  const body = precise && abs < 100 ? inr2.format(abs) : inr0.format(Math.round(abs));
  return `${sign}₹${body}`;
}

/** 23% — rounded; null/NaN become an em dash. */
export function formatPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** "1 server" / "3 servers". */
export function plural(n: number, word: string, many = `${word}s`): string {
  return `${n} ${n === 1 ? word : many}`;
}

/** "just now", "3 s ago", "5 min ago", "2 h ago", "4 d ago". Future times read as "just now". */
export function timeAgo(iso: string | number | Date | null | undefined, now: number = Date.now()): string {
  if (iso === null || iso === undefined) return "never";
  const t = iso instanceof Date ? iso.getTime() : typeof iso === "number" ? iso : Date.parse(withZone(iso));
  if (!Number.isFinite(t)) return "never";
  const s = Math.floor((now - t) / 1000);
  if (s < 2) return "just now";
  if (s < 60) return `${s} s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.floor(h / 24)} d ago`;
}

/** The backend sends UTC; SQLite values can come back without a zone, so treat those as UTC too. */
export function withZone(iso: string): string {
  return /([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`;
}

/** "14:05" in the viewer's local time. */
export function formatClock(iso: string): string {
  return new Date(withZone(iso)).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
