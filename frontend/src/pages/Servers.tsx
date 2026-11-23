import { useStats } from "../api/hooks";
import { ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { SkeletonCard } from "../components/Skeleton";
import { StatNumber } from "../components/StatNumber";
import { formatInr, formatPct, plural } from "../lib/format";
import { ServerIcon } from "../lib/icons";

export function Servers() {
  const stats = useStats();
  return (
    <div>
      <PageHeader title="Servers" sentence="Every server that reports to OptiServe, and how busy it is." />
      {stats.isPending ? (
        <SkeletonCard />
      ) : stats.isError ? (
        <Card>
          <ErrorState error={stats.error} onRetry={() => void stats.refetch()} />
        </Card>
      ) : stats.data.servers === 0 ? (
        <Card>
          <EmptyState
            icon={ServerIcon}
            title="No servers yet"
            action={<ButtonLink to="/connect">Connect a server</ButtonLink>}
          >
            Servers appear here as soon as the OptiServe agent or your AWS account sends their first numbers.
          </EmptyState>
        </Card>
      ) : (
        <Card title={`${plural(stats.data.servers, "server")} running`}>
          <div className="grid gap-6 sm:grid-cols-3">
            <StatNumber value={stats.data.servers} label={stats.data.servers === 1 ? "server running" : "servers running"} />
            <StatNumber value={formatPct(stats.data.avg_busy_pct)} label="busy on average" />
            <StatNumber value={formatInr(stats.data.monthly_cost_inr)} label="per month" />
          </div>
        </Card>
      )}
    </div>
  );
}
