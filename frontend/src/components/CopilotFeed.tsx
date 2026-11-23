// Copilot feed: suggestion cards with Approve / Not now, and live progress Approved → Changing… → Done.
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { POLL_FAST, useActions, useApprove, useRecommendations, useReject } from "../api/hooks";
import type { Action, Recommendation, RecommendationStatus } from "../api/types";
import { cn } from "../lib/cn";
import { formatInr } from "../lib/format";
import { CheckIcon, CopilotIcon, ErrorIcon, SpinnerIcon } from "../lib/icons";
import { Button } from "./Button";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { ErrorState } from "./ErrorState";
import { Pill } from "./Pill";
import { Skeleton } from "./Skeleton";
import { useToast } from "./Toast";
import { UpdatedAgo } from "./UpdatedAgo";

/** Done and failed cards are fetched too, but only shown for suggestions approved here. */
export const FEED_STATUSES: RecommendationStatus[] = ["pending", "blocked", "approved", "executing", "done", "failed"];
const OPEN = new Set<RecommendationStatus>(["pending", "blocked", "approved", "executing"]);

/** Which progress step a status has reached: 0 Approved, 1 Changing…, 2 Done; null when not approved. */
export function progressStep(status: RecommendationStatus): number | null {
  if (status === "approved") return 0;
  if (status === "executing") return 1;
  if (status === "done" || status === "failed") return 2;
  return null;
}

/** "Saves ₹1,200/month", "Avoids running out of room", or nothing. */
export function impactText(rec: Recommendation): string | null {
  if (rec.savings_month_inr > 0) return `Saves ${formatInr(rec.savings_month_inr)}/month`;
  if (rec.kind === "scale_up") return "Avoids running out of room";
  return null;
}

function actionTitle(rec: Recommendation): string {
  if (rec.kind === "scale_up") return `Add ${rec.to_count - rec.from_count === 1 ? "a server" : `${rec.to_count - rec.from_count} servers`} to ${rec.group_name}`;
  if (rec.kind === "scale_down") return `Remove a server from ${rec.group_name}`;
  if (rec.kind === "stop_idle") return `Stop ${rec.server_name ?? "an idle server"}`;
  return rec.group_name;
}

function Progress({ rec, action }: { rec: Recommendation; action: Action | undefined }) {
  const step = progressStep(rec.status) ?? 0;
  const failed = rec.status === "failed";
  const labels = ["Approved", "Changing…", failed ? "Didn't work" : "Done"];
  return (
    <div className="mt-3" role="status" aria-live="polite">
      <ol className="flex items-center gap-2 text-xs font-medium">
        {labels.map((label, i) => {
          const reached = i <= step;
          const current = i === step;
          const bad = failed && i === 2;
          return (
            <li key={label} className="flex items-center gap-2">
              {i > 0 && <span className={cn("h-px w-5 sm:w-8", reached ? "bg-accent" : "bg-line")} aria-hidden />}
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5",
                  bad ? "bg-danger-soft text-danger" : reached ? (i === 2 ? "bg-good-soft text-good" : "bg-accent-soft text-accent") : "text-muted",
                )}
              >
                {bad ? (
                  <ErrorIcon className="size-3.5" aria-hidden />
                ) : current && i < 2 ? (
                  <SpinnerIcon className="size-3.5 animate-spin" aria-hidden />
                ) : reached ? (
                  <CheckIcon className="size-3.5" aria-hidden />
                ) : null}
                {label}
              </span>
            </li>
          );
        })}
      </ol>
      {rec.status === "done" && action?.result === "dry_run" && (
        <p className="mt-2 text-xs text-muted">Practice run: nothing was changed in AWS (dry run is on).</p>
      )}
      {failed && <p className="mt-2 text-xs text-danger">{rec.blocked_reason ?? "AWS did not make the change. See Activity for details."}</p>}
    </div>
  );
}

export function FeedCard({
  rec,
  action,
  onApproved,
}: {
  rec: Recommendation;
  action: Action | undefined;
  onApproved: (id: number) => void;
}) {
  const approve = useApprove();
  const reject = useReject();
  const toast = useToast();
  const impact = impactText(rec);
  const inFlight = progressStep(rec.status) !== null;
  const blocked = rec.status === "blocked";
  const actionable = rec.status === "pending" && rec.kind !== "hold";

  return (
    <article className="rounded-2xl border border-line/70 bg-white/80 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm font-semibold text-ink">{actionTitle(rec)}</h3>
        {blocked && <Pill tone="warn">On hold</Pill>}
        {actionable && !rec.can_execute && <Pill>Suggestion only</Pill>}
      </div>
      <p className="mt-1.5 text-ink-soft">{rec.reason}</p>
      {impact && <p className="mt-2 text-sm font-medium text-good">{impact}</p>}
      {blocked && rec.blocked_reason && (
        <p className="mt-2 rounded-xl bg-warn-soft px-3 py-2 text-sm text-ink-soft">
          <span className="font-medium text-warn">Why it's on hold: </span>
          {rec.blocked_reason}
        </p>
      )}
      {actionable && !rec.can_execute && rec.recommendation_only_reason && (
        <p className="mt-2 text-xs text-muted">{rec.recommendation_only_reason}</p>
      )}
      {inFlight ? (
        <Progress rec={rec} action={action} />
      ) : (
        actionable && (
          <div className="mt-4 flex flex-wrap gap-2">
            {rec.can_execute && (
              <Button
                loading={approve.isPending}
                disabled={reject.isPending}
                onClick={() =>
                  approve.mutate(rec.id, {
                    onSuccess: () => onApproved(rec.id),
                    onError: (e) => toast.show(e.message, "error"),
                  })
                }
              >
                Approve
              </Button>
            )}
            <Button
              variant="secondary"
              loading={reject.isPending}
              disabled={approve.isPending}
              onClick={() => reject.mutate(rec.id, { onError: (e) => toast.show(e.message, "error") })}
            >
              Not now
            </Button>
          </div>
        )
      )}
    </article>
  );
}

export function CopilotFeed() {
  const recs = useRecommendations(FEED_STATUSES, { poll: POLL_FAST });
  const [watched, setWatched] = useState<ReadonlySet<number>>(() => new Set());
  const actions = useActions({ poll: watched.size ? POLL_FAST : 0, limit: 20 });
  const reduce = useReducedMotion();

  const shown = (recs.data ?? []).filter((r) => OPEN.has(r.status) || watched.has(r.id));
  const actionFor = (id: number) => actions.data?.find((a) => a.recommendation_id === id);

  return (
    <Card title="Copilot" action={recs.dataUpdatedAt ? <UpdatedAgo at={recs.dataUpdatedAt} /> : null}>
      {recs.isPending ? (
        <Skeleton lines={4} />
      ) : recs.isError ? (
        <ErrorState error={recs.error} onRetry={() => void recs.refetch()} />
      ) : shown.length === 0 ? (
        <EmptyState icon={CopilotIcon} title="Nothing to change right now">
          OptiServe checks your servers every minute. When adding or removing a server would help, a suggestion appears
          here for you to approve.
        </EmptyState>
      ) : (
        <ul className="space-y-3">
          <AnimatePresence initial={false}>
            {shown.map((r) => (
              <motion.li
                key={r.id}
                layout={!reduce}
                initial={reduce ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduce ? { opacity: 0 } : { opacity: 0, y: -6 }}
                transition={{ duration: 0.2 }}
              >
                <FeedCard
                  rec={r}
                  action={actionFor(r.id)}
                  onApproved={(id) => setWatched((prev) => new Set(prev).add(id))}
                />
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </Card>
  );
}
