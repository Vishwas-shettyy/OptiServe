import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useServers } from "../api/hooks";
import type { FleetStatus, ServerRow } from "../api/types";
import { ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { Skeleton } from "../components/Skeleton";
import { ManagedPill, StatusPill } from "../components/StatusPill";
import { UpdatedAgo } from "../components/UpdatedAgo";
import { cn } from "../lib/cn";
import { formatInr, formatPct } from "../lib/format";
import { NextIcon, ServerIcon } from "../lib/icons";

export type Filter = "all" | "busy" | "idle" | "unhealthy";

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "busy", label: "Busy" },
  { id: "idle", label: "Idle" },
  { id: "unhealthy", label: "Unhealthy" },
];

/** Rows matching the search text (name, group or type) and the status filter. */
export function filterServers(rows: ServerRow[], search: string, filter: Filter): ServerRow[] {
  const q = search.trim().toLowerCase();
  return rows.filter(
    (r) =>
      (filter === "all" || r.status === (filter as FleetStatus)) &&
      (!q || [r.name, r.group_name, r.instance_type ?? ""].some((v) => v.toLowerCase().includes(q))),
  );
}

function stateWord(r: ServerRow): string {
  return r.state === "running" ? "Running" : r.state === "stopped" ? "Stopped" : "Unknown";
}

function Cost({ r }: { r: ServerRow }) {
  if (r.state === "stopped") return <span className="text-muted">₹0</span>;
  if (r.monthly_cost_inr === null) return <span className="text-muted">Price not set</span>;
  return <span>{formatInr(r.monthly_cost_inr)}</span>;
}

function BusyBar({ pct }: { pct: number | null }) {
  const v = Math.min(Math.max(pct ?? 0, 0), 100);
  const color = v >= 80 ? "bg-red-500" : v >= 50 ? "bg-amber-500" : "bg-blue-500";
  return (
    <span className="flex items-center gap-2">
      <span className="w-10 text-right font-medium tabular text-ink">{formatPct(pct)}</span>
      <span className="hidden h-1.5 w-16 overflow-hidden rounded-full bg-slate-100 lg:block" aria-hidden>
        <span className={cn("block h-full rounded-full", color)} style={{ width: `${v}%` }} />
      </span>
    </span>
  );
}

function Table({ rows }: { rows: ServerRow[] }) {
  return (
    <>
      <table className="hidden w-full text-sm md:table">
        <thead>
          <tr className="border-b border-line text-left text-xs font-medium tracking-wide text-muted uppercase">
            <th className="py-2.5 pr-4 font-medium">Server</th>
            <th className="py-2.5 pr-4 font-medium">Busy</th>
            <th className="py-2.5 pr-4 font-medium">State</th>
            <th className="py-2.5 pr-4 font-medium">Cost / month</th>
            <th className="py-2.5 pr-4 font-medium">Status</th>
            <th className="py-2.5 font-medium">OptiServe can act</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line/70">
          {rows.map((r) => (
            <tr key={r.id} className="group hover:bg-slate-50/70">
              <td className="py-3 pr-4">
                <Link to={`/servers/${r.id}`} className="font-medium text-ink group-hover:text-accent">
                  {r.name}
                </Link>
                <p className="text-xs text-muted">
                  {r.group_name}
                  {r.instance_type ? ` · ${r.instance_type}` : ""}
                </p>
              </td>
              <td className="py-3 pr-4">
                {r.status === "stopped" ? <span className="text-muted">—</span> : <BusyBar pct={r.cpu_pct} />}
              </td>
              <td className="py-3 pr-4 text-ink-soft">{stateWord(r)}</td>
              <td className="py-3 pr-4 tabular">
                <Cost r={r} />
              </td>
              <td className="py-3 pr-4">
                <StatusPill status={r.status} />
              </td>
              <td className="py-3">
                <ManagedPill managed={r.managed} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <ul className="divide-y divide-line/70 md:hidden">
        {rows.map((r) => (
          <li key={r.id}>
            <Link to={`/servers/${r.id}`} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2">
                  <span className="truncate font-medium text-ink">{r.name}</span>
                  <StatusPill status={r.status} />
                </p>
                <p className="mt-0.5 text-xs text-muted">
                  {r.status === "stopped" ? "Stopped" : `${formatPct(r.cpu_pct)} busy`} · <Cost r={r} />
                  {r.monthly_cost_inr !== null && r.state !== "stopped" ? "/month" : ""} · {r.group_name}
                </p>
              </div>
              <NextIcon className="size-4 shrink-0 text-muted" aria-hidden />
            </Link>
          </li>
        ))}
      </ul>
    </>
  );
}

export function Servers() {
  const servers = useServers();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  const rows = useMemo(() => filterServers(servers.data ?? [], search, filter), [servers.data, search, filter]);
  const count = (f: Filter) => filterServers(servers.data ?? [], "", f).length;

  return (
    <div>
      <PageHeader
        title="Servers"
        sentence="Every server that reports to OptiServe, and how busy it is."
        aside={servers.dataUpdatedAt ? <UpdatedAgo at={servers.dataUpdatedAt} /> : null}
      />
      {servers.isPending ? (
        <Card>
          <Skeleton lines={6} />
        </Card>
      ) : servers.isError ? (
        <Card>
          <ErrorState error={servers.error} onRetry={() => void servers.refetch()} />
        </Card>
      ) : servers.data.length === 0 ? (
        <Card>
          <EmptyState icon={ServerIcon} title="No servers yet" action={<ButtonLink to="/connect">Connect a server</ButtonLink>}>
            Servers appear here as soon as the OptiServe agent or your AWS account sends their first numbers.
          </EmptyState>
        </Card>
      ) : (
        <Card>
          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <input
              type="search"
              aria-label="Search servers"
              placeholder="Search by name, group or type"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="h-10 w-full rounded-xl border border-line bg-white px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent-ring/50 sm:max-w-xs"
            />
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Show">
              {FILTERS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  aria-pressed={filter === f.id}
                  onClick={() => setFilter(f.id)}
                  className={cn(
                    "h-8 rounded-full px-3 text-sm font-medium transition-colors",
                    filter === f.id ? "bg-accent text-white" : "bg-slate-100 text-ink-soft hover:bg-slate-200",
                  )}
                >
                  {f.label} <span className="tabular opacity-70">{count(f.id)}</span>
                </button>
              ))}
            </div>
          </div>
          {rows.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted">
              No servers match. Clear the search or pick another filter.
            </p>
          ) : (
            <Table rows={rows} />
          )}
        </Card>
      )}
    </div>
  );
}
