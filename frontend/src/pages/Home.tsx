import { POLL_FAST, useRecommendations, useStats } from "../api/hooks";
import type { Recommendation, Stats } from "../api/types";
import { Navigate } from "react-router-dom";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { Pill } from "../components/Pill";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatNumber } from "../components/StatNumber";
import { UpdatedAgo } from "../components/UpdatedAgo";
import { formatInr, formatPct } from "../lib/format";
import { GaugeIcon } from "../lib/icons";

/** One sentence a first-time visitor understands in 5 seconds. */
export function headline(stats: Stats): string {
  if (stats.avg_busy_pct === null) return "Your servers are connected. OptiServe is waiting for their first numbers.";
  const busy = `Your servers are ${formatPct(stats.avg_busy_pct)} busy.`;
  if (stats.potential_savings_inr > 0) return `${busy} You can save ${formatInr(stats.potential_savings_inr)}/month.`;
  return `${busy} Nothing to change right now.`;
}

function FeedItem({ rec }: { rec: Recommendation }) {
  const impact =
    rec.savings_month_inr > 0
      ? `Saves ${formatInr(rec.savings_month_inr)}/month`
      : rec.kind === "scale_up"
        ? "Avoids running out of room"
        : null;
  return (
    <li className="rounded-2xl border border-line/70 bg-white/70 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-ink">{rec.group_name}</span>
        {rec.status === "blocked" && <Pill tone="warn">On hold</Pill>}
        {!rec.can_execute && rec.kind !== "hold" && <Pill>Suggestion only</Pill>}
      </div>
      <p className="mt-1.5 text-ink-soft">{rec.reason}</p>
      {impact && <p className="mt-2 text-sm font-medium text-good">{impact}</p>}
    </li>
  );
}

function CopilotFeed() {
  const recs = useRecommendations(undefined, { poll: POLL_FAST });
  return (
    <Card title="Copilot" action={recs.dataUpdatedAt ? <UpdatedAgo at={recs.dataUpdatedAt} /> : null}>
      {recs.isPending ? (
        <Skeleton lines={3} />
      ) : recs.isError ? (
        <ErrorState error={recs.error} onRetry={() => void recs.refetch()} />
      ) : recs.data.length === 0 ? (
        <EmptyState icon={GaugeIcon} title="No suggestions yet">
          OptiServe checks your servers every minute. When adding or removing a server would help, a suggestion
          appears here for you to approve.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          {recs.data.map((r) => (
            <FeedItem key={r.id} rec={r} />
          ))}
        </ul>
      )}
    </Card>
  );
}

export function Home() {
  const stats = useStats({ poll: POLL_FAST });

  if (stats.isPending) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-2/3" />
        <SkeletonCard />
      </div>
    );
  }
  if (stats.isError) {
    return (
      <Card>
        <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />
      </Card>
    );
  }
  // No servers yet: onboarding is the only useful next step.
  if (stats.data.servers === 0) return <Navigate to="/connect" replace />;

  const s = stats.data;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="max-w-3xl text-2xl leading-tight font-semibold sm:text-4xl">{headline(s)}</h1>
        <UpdatedAgo at={stats.dataUpdatedAt} />
      </div>
      <Card>
        <div className="grid gap-6 sm:grid-cols-3">
          <StatNumber value={formatPct(s.avg_busy_pct)} label="busy" hint={`Across ${s.servers} running servers`} />
          <StatNumber
            value={formatInr(s.potential_savings_inr)}
            label="per month you can save"
            tone={s.potential_savings_inr > 0 ? "accent" : "default"}
          />
          <StatNumber value={formatInr(s.realized_savings_inr)} label="saved so far" tone="good" />
        </div>
      </Card>
      <CopilotFeed />
    </div>
  );
}
