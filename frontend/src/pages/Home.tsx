import { Navigate } from "react-router-dom";
import { POLL_FAST, useGroups, useStats, useWeather } from "../api/hooks";
import type { Stats } from "../api/types";
import { CapacityWeather } from "../components/CapacityWeather";
import { Card } from "../components/Card";
import { CopilotFeed } from "../components/CopilotFeed";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LiveFleet } from "../components/LiveFleet";
import { SavingsCounter } from "../components/SavingsCounter";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { UpdatedAgo } from "../components/UpdatedAgo";
import { formatInr, formatPct } from "../lib/format";
import { CloudIcon, ServerIcon } from "../lib/icons";

/** One sentence a first-time visitor understands in 5 seconds. */
export function headline(stats: Stats): string {
  if (stats.avg_busy_pct === null) return "Your servers are connected. OptiServe is waiting for their first numbers.";
  const busy = `Your servers are ${formatPct(stats.avg_busy_pct)} busy.`;
  if (stats.potential_savings_inr > 0) return `${busy} You can save ${formatInr(stats.potential_savings_inr)}/month.`;
  return `${busy} Nothing to change right now.`;
}

function FleetCard() {
  const groups = useGroups({ poll: POLL_FAST });
  return (
    <Card title="Live fleet" action={groups.dataUpdatedAt ? <UpdatedAgo at={groups.dataUpdatedAt} /> : null}>
      {groups.isPending ? (
        <div className="flex flex-wrap gap-3" aria-busy>
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="size-16 rounded-2xl" />
          ))}
        </div>
      ) : groups.isError ? (
        <ErrorState error={groups.error} onRetry={() => void groups.refetch()} />
      ) : groups.data.length === 0 ? (
        <EmptyState icon={ServerIcon} title="No servers reporting">
          Install the agent or connect AWS from the Connect page. Each server appears here as a tile within a minute.
        </EmptyState>
      ) : (
        <LiveFleet groups={groups.data} />
      )}
    </Card>
  );
}

function WeatherCard() {
  const weather = useWeather({ poll: POLL_FAST });
  const horizon = weather.data?.horizon ?? (weather.data?.live_mode ? "60 min" : "24 h");
  return (
    <Card
      title={`Capacity weather · next ${horizon}`}
      action={weather.dataUpdatedAt ? <UpdatedAgo at={weather.dataUpdatedAt} /> : null}
    >
      {weather.isPending ? (
        <div className="space-y-4">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-10" />
        </div>
      ) : weather.isError ? (
        <ErrorState error={weather.error} onRetry={() => void weather.refetch()} />
      ) : weather.data.slots.length === 0 ? (
        <EmptyState icon={CloudIcon} title="OptiServe is learning" className="py-6 sm:py-8">
          {weather.data.message}
        </EmptyState>
      ) : (
        <CapacityWeather weather={weather.data} />
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
        <div className="grid gap-6 lg:grid-cols-3">
          <SkeletonCard className="lg:col-span-2" />
          <SkeletonCard />
        </div>
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="max-w-3xl text-2xl leading-tight font-semibold sm:text-4xl">{headline(s)}</h1>
          <div className="mt-2">
            <UpdatedAgo at={stats.dataUpdatedAt} />
          </div>
        </div>
        <SavingsCounter value={s.realized_savings_inr} />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <FleetCard />
          <WeatherCard />
        </div>
        <div className="min-w-0">
          <CopilotFeed />
        </div>
      </div>
    </div>
  );
}
