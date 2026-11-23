import { useActions } from "../api/hooks";
import type { Action } from "../api/types";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { Pill, type PillTone } from "../components/Pill";
import { Skeleton } from "../components/Skeleton";
import { UpdatedAgo } from "../components/UpdatedAgo";
import { formatInr, plural, timeAgo } from "../lib/format";
import { ActivityIcon } from "../lib/icons";

/** "Added 1 server to web" in plain words. */
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

function outcome(a: Action): { label: string; tone: PillTone } {
  if (a.result === "done") return { label: "Done", tone: "good" };
  if (a.result === "dry_run") return { label: "Dry run", tone: "neutral" };
  if (a.result === "failed") return { label: "Failed", tone: "danger" };
  if (a.status === "blocked") return { label: "Stopped by safety check", tone: "warn" };
  return { label: "Changing…", tone: "accent" };
}

function Row({ a }: { a: Action }) {
  const o = outcome(a);
  const message = typeof a.details.message === "string" ? a.details.message : null;
  return (
    <li className="flex flex-col gap-1 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <p className="font-medium text-ink">{describeAction(a)}</p>
        <p className="text-sm text-muted">
          Approved by {a.approved_by} · {timeAgo(a.approved_at)}
        </p>
        {message && <p className="mt-1 text-sm text-ink-soft">{message}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-3">
        {a.realized_savings_inr > 0 && (
          <span className="text-sm font-medium text-good">{formatInr(a.realized_savings_inr)} saved</span>
        )}
        <Pill tone={o.tone}>{o.label}</Pill>
      </div>
    </li>
  );
}

export function Activity() {
  const actions = useActions();
  return (
    <div>
      <PageHeader
        title="Activity"
        sentence="Every change you approved, who approved it and what happened."
        aside={actions.dataUpdatedAt ? <UpdatedAgo at={actions.dataUpdatedAt} /> : null}
      />
      <Card>
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
          <ul className="divide-y divide-line/70">
            {actions.data.map((a) => (
              <Row key={a.id} a={a} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
