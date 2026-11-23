import { Line, LineChart, ReferenceLine, ResponsiveContainer, YAxis } from "recharts";
import { useActionChart, useActions, useStats } from "../api/hooks";
import type { Action } from "../api/types";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { Pill, type PillTone } from "../components/Pill";
import { Skeleton } from "../components/Skeleton";
import { StatNumber } from "../components/StatNumber";
import { UpdatedAgo } from "../components/UpdatedAgo";
import { cn } from "../lib/cn";
import { formatInr, formatPct, plural, timeAgo, withZone } from "../lib/format";
import { ActivityIcon } from "../lib/icons";

/** "Add 1 server to web" in plain words. */
export function describeAction(a: Action): string {
  const group = a.group_name ?? "a group";
  const n = Math.abs((a.to_count ?? 0) - (a.from_count ?? 0));
  switch (a.kind) {
    case "scale_up":
      return `Add ${plural(n, "server")} to ${group}`;
    case "scale_down":
      return `Remove ${plural(n, "server")} from ${group}`;
    case "stop_idle":
      return `Stop an idle server in ${group}`;
    default:
      return `Change ${group}`;
  }
}

export function outcome(a: Action): { label: string; tone: PillTone } {
  if (a.result === "done") return { label: "Done", tone: "good" };
  if (a.result === "dry_run") return { label: "Dry run: nothing changed", tone: "neutral" };
  if (a.result === "failed") return { label: "Failed", tone: "danger" };
  if (a.status === "blocked") return { label: "Stopped by safety check", tone: "warn" };
  return { label: "Changing…", tone: "accent" };
}

function when(iso: string): string {
  const d = new Date(withZone(iso));
  return d.toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function MiniChart({ a }: { a: Action }) {
  const chart = useActionChart(a.id);
  if (chart.isPending) return <Skeleton className="h-16 w-full sm:w-48" />;
  if (chart.isError || chart.data.points.length < 2) {
    return <p className="text-xs text-muted sm:w-48">Not enough numbers around this change for a chart.</p>;
  }
  const c = chart.data;
  const data = c.points.map((p) => ({ t: Date.parse(withZone(p.ts)), load: p.load }));
  const at = c.changed_at ? Date.parse(withZone(c.changed_at)) : null;
  return (
    <figure className="w-full sm:w-48">
      <div className="h-16" role="img" aria-label={`Load before and after the change, ${c.before_servers} to ${c.after_servers} servers`}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
            <YAxis hide domain={[0, "dataMax"]} />
            <Line dataKey="load" stroke="#2563eb" strokeWidth={1.75} dot={false} isAnimationActive={false} />
            {at !== null && <ReferenceLine x={at} stroke="#94a3b8" strokeDasharray="3 3" />}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <figcaption className="mt-1 flex justify-between text-[11px] text-muted">
        <span>Before: {c.before_servers ?? "—"}</span>
        <span>After: {c.after_servers ?? "—"} servers</span>
      </figcaption>
    </figure>
  );
}

function Entry({ a, last }: { a: Action; last: boolean }) {
  const o = outcome(a);
  const message = typeof a.details.message === "string" ? a.details.message : null;
  const dot = { good: "bg-good", danger: "bg-danger", warn: "bg-warn", accent: "bg-accent", neutral: "bg-slate-400" }[o.tone];
  return (
    <li className="relative flex gap-4 pb-6">
      {!last && <span className="absolute top-4 bottom-0 left-[7px] w-px bg-line" aria-hidden />}
      <span className={cn("relative mt-1.5 size-[15px] shrink-0 rounded-full border-4 border-white shadow", dot)} aria-hidden />
      <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-ink">{describeAction(a)}</p>
            <Pill tone={o.tone}>{o.label}</Pill>
          </div>
          <p className="mt-0.5 text-sm text-muted">
            Approved by {a.approved_by} · <time dateTime={a.approved_at}>{when(a.approved_at)}</time> ({timeAgo(a.approved_at)})
          </p>
          {message && <p className="mt-1 text-sm text-ink-soft">{message}</p>}
          {a.realized_savings_inr > 0 && (
            <p className="mt-1 text-sm font-medium text-good">{formatInr(a.realized_savings_inr, { precise: true })} saved so far</p>
          )}
        </div>
        <MiniChart a={a} />
      </div>
    </li>
  );
}

function Proof() {
  const stats = useStats();
  if (stats.isPending) return <Skeleton className="h-14" />;
  if (stats.isError) return <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />;
  const s = stats.data;
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      <StatNumber
        value={formatInr(s.realized_savings_inr, { precise: true })}
        label="saved so far"
        tone="good"
        hint="Servers removed × hours since × their price. Dry runs save nothing."
      />
      <StatNumber
        value={s.accuracy_pct === null ? "—" : formatPct(s.accuracy_pct)}
        label="forecast accuracy"
        hint={
          s.accuracy_pct === null
            ? "Measured once forecasts can be compared with what really happened."
            : `How close the last 24 h of forecasts were to reality (${s.accuracy_points} minutes checked).`
        }
      />
    </div>
  );
}

export function Activity() {
  const actions = useActions();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Activity"
        sentence="Every change you approved, who approved it and what happened."
        aside={actions.dataUpdatedAt ? <UpdatedAgo at={actions.dataUpdatedAt} /> : null}
      />
      <Card>
        <Proof />
      </Card>
      <Card title="Timeline">
        {actions.isPending ? (
          <Skeleton lines={4} />
        ) : actions.isError ? (
          <ErrorState error={actions.error} onRetry={() => void actions.refetch()} />
        ) : actions.data.length === 0 ? (
          <EmptyState icon={ActivityIcon} title="Nothing has changed yet">
            OptiServe never changes a server without your approval. When you approve a suggestion on Home, it shows up
            here with the result.
          </EmptyState>
        ) : (
          <ol>
            {actions.data.map((a, i) => (
              <Entry key={a.id} a={a} last={i === actions.data.length - 1} />
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
