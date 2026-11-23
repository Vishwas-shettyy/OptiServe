import { useAgentTokens, useConnections, useHealth, useRevokeAgentToken } from "../api/hooks";
import { Button, ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { Pill } from "../components/Pill";
import { Skeleton } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import { timeAgo } from "../lib/format";
import { CloudIcon, KeyIcon } from "../lib/icons";

function Connections() {
  const conns = useConnections();
  return (
    <Card title="Connections">
      {conns.isPending ? (
        <Skeleton lines={2} />
      ) : conns.isError ? (
        <ErrorState error={conns.error} onRetry={() => void conns.refetch()} />
      ) : conns.data.length === 0 ? (
        <EmptyState icon={CloudIcon} title="Nothing connected" action={<ButtonLink to="/connect">Connect a server</ButtonLink>}>
          Connect your AWS account or install the agent on a server to start.
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line/70">
          {conns.data.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <div>
                <p className="font-medium text-ink">{c.name}</p>
                <p className="text-sm text-muted">
                  {c.kind === "aws" ? `AWS · ${c.region ?? ""}` : "Agent"} · last checked {timeAgo(c.last_sync_at)}
                </p>
                {c.error_message && <p className="mt-1 text-sm text-danger">{c.error_message}</p>}
              </div>
              <Pill tone={c.status === "ok" ? "good" : "danger"}>{c.status === "ok" ? "Working" : "Needs attention"}</Pill>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function AgentTokens() {
  const tokens = useAgentTokens();
  const revoke = useRevokeAgentToken();
  const toast = useToast();
  return (
    <Card title="Agent tokens">
      {tokens.isPending ? (
        <Skeleton lines={2} />
      ) : tokens.isError ? (
        <ErrorState error={tokens.error} onRetry={() => void tokens.refetch()} />
      ) : tokens.data.length === 0 ? (
        <EmptyState icon={KeyIcon} title="No agent tokens" action={<ButtonLink to="/connect" variant="secondary">Install the agent</ButtonLink>}>
          Each server running the OptiServe agent uses a token to send its numbers. You create one when you install
          the agent.
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line/70">
          {tokens.data.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <div>
                <p className="font-medium text-ink">{t.label}</p>
                <p className="text-sm text-muted">Created {timeAgo(t.created_at)}</p>
              </div>
              {t.revoked ? (
                <Pill>Turned off</Pill>
              ) : (
                <Button
                  variant="secondary"
                  size="sm"
                  loading={revoke.isPending && revoke.variables === t.id}
                  onClick={() =>
                    revoke.mutate(t.id, {
                      onSuccess: () => toast.show(`${t.label} can no longer send data.`, "success"),
                      onError: (e) => toast.show(e.message, "error"),
                    })
                  }
                >
                  Turn off
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Modes() {
  const health = useHealth();
  if (!health.data) return null;
  const { live_mode, dry_run } = health.data;
  return (
    <Card title="How OptiServe acts">
      <ul className="space-y-3 text-sm text-ink-soft">
        <li>
          <span className="font-medium text-ink">{dry_run ? "Dry run is on." : "Dry run is off."}</span>{" "}
          {dry_run
            ? "Approved changes are logged but nothing on your servers is changed."
            : "Approved changes are made on groups tagged optiserve:managed=true."}
        </li>
        <li>
          <span className="font-medium text-ink">{live_mode ? "Live mode is on." : "Live mode is off."}</span>{" "}
          {live_mode
            ? "OptiServe reacts within minutes, using shorter windows on the same real data."
            : "OptiServe looks at days of history before suggesting changes."}
        </li>
      </ul>
      <p className="mt-3 text-xs text-muted">Both are set in the backend's .env file.</p>
    </Card>
  );
}

export function Settings() {
  return (
    <div>
      <PageHeader title="Settings" sentence="Your connections, agent tokens and how OptiServe acts." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Connections />
        <AgentTokens />
        <Modes />
      </div>
    </div>
  );
}
