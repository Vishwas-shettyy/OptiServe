import { useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { ApiError } from "../api/client";
import { POLL_FAST, keys, useActions, useServer } from "../api/hooks";
import type { SafetyCheck, ServerDetail as Detail } from "../api/types";
import { ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { FeedCard, progressStep } from "../components/CopilotFeed";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadChart } from "../components/LoadChart";
import { Skeleton, SkeletonCard } from "../components/Skeleton";
import { StatNumber } from "../components/StatNumber";
import { ManagedPill, StatusPill } from "../components/StatusPill";
import { UpdatedAgo } from "../components/UpdatedAgo";
import { cn } from "../lib/cn";
import { formatInr, formatPct } from "../lib/format";
import { BackIcon, CheckIcon, CopilotIcon, ErrorIcon, InfoIcon, ServerIcon, ShieldIcon } from "../lib/icons";

const checkLook: Record<SafetyCheck["status"], { word: string; className: string; icon: typeof CheckIcon }> = {
  pass: { word: "OK", className: "bg-good-soft text-good", icon: CheckIcon },
  adjusted: { word: "Adjusted", className: "bg-accent-soft text-accent", icon: InfoIcon },
  blocked: { word: "Stopped a change", className: "bg-warn-soft text-warn", icon: ErrorIcon },
};

function Safety({ checks }: { checks: SafetyCheck[] }) {
  if (checks.length === 0) {
    return <p className="text-sm text-muted">Safety checks run once this group has sent a few minutes of numbers.</p>;
  }
  return (
    <ul className="space-y-2.5">
      {checks.map((c) => {
        const l = checkLook[c.status];
        const Icon = l.icon;
        return (
          <li key={c.number} className="flex gap-3" data-status={c.status}>
            <span className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full", l.className)} aria-hidden>
              <Icon className="size-3.5" />
            </span>
            <div className="min-w-0 text-sm">
              <p className="font-medium text-ink">
                {c.rule} <span className="sr-only">: {l.word}</span>
              </p>
              <p className="text-ink-soft">{c.message}</p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Suggestion({ detail }: { detail: Detail }) {
  const qc = useQueryClient();
  const rec = detail.recommendation;
  const inFlight = rec ? progressStep(rec.status) !== null : false;
  const actions = useActions({ poll: inFlight ? POLL_FAST : 0, limit: 20 });
  if (!rec) {
    return (
      <EmptyState icon={CopilotIcon} title="Nothing to change" className="py-6 sm:py-6">
        OptiServe has no suggestion for {detail.server.group_name} right now.
      </EmptyState>
    );
  }
  return (
    <FeedCard
      rec={rec}
      action={actions.data?.find((a) => a.recommendation_id === rec.id)}
      onApproved={() => void qc.invalidateQueries({ queryKey: keys.server(detail.server.id) })}
    />
  );
}

function Body({ d, updatedAt }: { d: Detail; updatedAt: number }) {
  const s = d.server;
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <ButtonLink to="/servers" variant="ghost" size="sm" className="-ml-3 mb-2" icon={<BackIcon className="size-4" aria-hidden />}>
            All servers
          </ButtonLink>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold sm:text-3xl">{s.name}</h1>
            <StatusPill status={s.status} />
            <ManagedPill managed={s.managed} />
          </div>
          <p className="mt-1 text-ink-soft">
            In {s.group_name}
            {s.instance_type ? ` · ${s.instance_type}` : ""} · {s.provider === "aws" ? "AWS" : "Agent"}
          </p>
        </div>
        <UpdatedAgo at={updatedAt} />
      </div>

      <Card>
        <div className="grid gap-6 sm:grid-cols-3">
          <StatNumber value={s.status === "stopped" ? "—" : formatPct(s.cpu_pct)} label="busy" />
          <StatNumber
            value={s.mem_pct === null ? "—" : formatPct(s.mem_pct)}
            label="memory used"
            hint={s.mem_pct === null && s.provider === "aws" ? "Needs the agent" : undefined}
          />
          <StatNumber
            value={s.monthly_cost_inr === null ? "—" : formatInr(s.monthly_cost_inr)}
            label="per month"
            hint={s.monthly_cost_inr === null && s.state !== "stopped" ? "Set a price in Settings" : undefined}
          />
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <Card title={`${s.group_name}: last hour and next hour`}>
            {d.chart.length === 0 ? (
              <EmptyState icon={ServerIcon} title="No numbers yet" className="py-8 sm:py-8">
                The chart fills in once this group has sent a few minutes of data.
              </EmptyState>
            ) : (
              <LoadChart points={d.chart} capacity={d.capacity} now={d.as_of} />
            )}
          </Card>
          <Card title="What OptiServe sees">
            <ul className="space-y-2 text-ink-soft">
              {d.sees.map((line) => (
                <li key={line} className="flex gap-2.5">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                  {line}
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="min-w-0 space-y-6">
          <Card title="Current suggestion">
            <Suggestion detail={d} />
          </Card>
          <Card
            title={
              <span className="inline-flex items-center gap-2">
                <ShieldIcon className="size-4 text-good" aria-hidden /> Safety checks
              </span>
            }
          >
            <Safety checks={d.safety} />
          </Card>
        </div>
      </div>
    </div>
  );
}

export function ServerDetail() {
  const { serverId } = useParams();
  const id = Number(serverId);
  const detail = useServer(id);

  if (!Number.isInteger(id) || id <= 0 || (detail.error instanceof ApiError && detail.error.status === 404)) {
    return (
      <Card>
        <EmptyState
          icon={ServerIcon}
          title="No details for this server yet"
          action={
            <ButtonLink to="/servers" variant="secondary">
              Back to servers
            </ButtonLink>
          }
        >
          This server isn't known to OptiServe. It may have been removed, or it hasn't sent its first numbers yet.
        </EmptyState>
      </Card>
    );
  }
  if (detail.isPending) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-1/3" />
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }
  if (detail.isError) {
    return (
      <Card>
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      </Card>
    );
  }
  return <Body d={detail.data} updatedAt={detail.dataUpdatedAt} />;
}
