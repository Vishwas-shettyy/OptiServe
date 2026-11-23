import { useState, type FormEvent, type ReactNode } from "react";
import {
  useAgentTokens,
  useAppSettings,
  useConnections,
  useCreateAgentToken,
  useRemoveConnection,
  useRevokeAgentToken,
  useServers,
  useSetPrice,
  useSyncConnection,
  useUpdateSettings,
} from "../api/hooks";
import type { AgentTokenCreated, AppSettings, Connection, ServerRow } from "../api/types";
import { Button, ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { PageHeader } from "../components/PageHeader";
import { Pill } from "../components/Pill";
import { Skeleton } from "../components/Skeleton";
import { useToast } from "../components/Toast";
import { cn } from "../lib/cn";
import { formatInr, plural, timeAgo } from "../lib/format";
import { CloudIcon, KeyIcon, ServerIcon, WarningIcon } from "../lib/icons";
import { CopyBox, installCommand } from "./Connect";

const inputClass =
  "h-9 rounded-xl border border-line bg-white px-3 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent-ring/50";

// ---------- connections ----------

function ConnectionRow({ c }: { c: Connection }) {
  const sync = useSyncConnection();
  const remove = useRemoveConnection();
  const toast = useToast();
  const [confirming, setConfirming] = useState(false);
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-medium text-ink">
            {c.name}
            <Pill tone={c.status === "ok" ? "good" : "danger"}>{c.status === "ok" ? "Working" : "Needs attention"}</Pill>
          </p>
          <p className="text-sm text-muted">
            {c.kind === "aws" ? `AWS · ${c.region ?? ""}` : "Agent"} · last checked {timeAgo(c.last_sync_at)}
          </p>
          {c.error_message && <p className="mt-1 text-sm text-danger">{c.error_message}</p>}
        </div>
        {c.kind === "aws" && !confirming && (
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              loading={sync.isPending}
              onClick={() =>
                sync.mutate(c.id, {
                  onSuccess: (r) => toast.show(`Synced ${plural(r.instances, "server")}.`, "success"),
                  onError: (e) => toast.show(e.message, "error"),
                })
              }
            >
              Sync now
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirming(true)}>
              Remove
            </Button>
          </div>
        )}
      </div>
      {confirming && (
        <div className="mt-3 rounded-xl bg-danger-soft p-3 text-sm" role="alertdialog" aria-label={`Remove ${c.name}?`}>
          <p className="text-ink-soft">
            OptiServe stops reading this account. Its servers and their numbers disappear from OptiServe; nothing changes
            in AWS. Activity keeps its history.
          </p>
          <div className="mt-3 flex gap-2">
            <Button
              variant="danger"
              size="sm"
              loading={remove.isPending}
              onClick={() =>
                remove.mutate(c.id, {
                  onSuccess: (r) => toast.show(`Removed. ${plural(r.servers_removed, "server")} no longer shown.`, "success"),
                  onError: (e) => {
                    setConfirming(false);
                    toast.show(e.message, "error");
                  },
                })
              }
            >
              Yes, remove
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setConfirming(false)}>
              Keep it
            </Button>
          </div>
        </div>
      )}
    </li>
  );
}

function Connections() {
  const conns = useConnections();
  return (
    <Card title="Connections" action={<ButtonLink to="/connect" variant="secondary" size="sm">Add</ButtonLink>}>
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
            <ConnectionRow key={c.id} c={c} />
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------- agent tokens ----------

function AgentTokens() {
  const tokens = useAgentTokens();
  const create = useCreateAgentToken();
  const revoke = useRevokeAgentToken();
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [fresh, setFresh] = useState<AgentTokenCreated | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!label.trim()) return;
    create.mutate(label.trim(), {
      onSuccess: (t) => {
        setFresh(t);
        setLabel("");
      },
      onError: (err) => toast.show(err.message, "error"),
    });
  }

  return (
    <Card title="Agent tokens">
      <form onSubmit={submit} className="mb-4 flex gap-2">
        <input
          className={cn(inputClass, "min-w-0 flex-1")}
          placeholder="Name, e.g. web-3"
          aria-label="New token name"
          value={label}
          maxLength={100}
          onChange={(e) => setLabel(e.target.value)}
        />
        <Button type="submit" size="sm" className="h-9" loading={create.isPending} disabled={!label.trim()}>
          Create token
        </Button>
      </form>
      {fresh && (
        <div className="mb-4 space-y-2">
          <p className="text-sm text-ink-soft">
            Install command for <span className="font-medium text-ink">{fresh.label}</span>. The key is shown only now.
          </p>
          <CopyBox label="Terminal on your server" text={installCommand(window.location.origin, fresh.token)} />
          <Button variant="ghost" size="sm" onClick={() => setFresh(null)}>
            Done
          </Button>
        </div>
      )}
      {tokens.isPending ? (
        <Skeleton lines={2} />
      ) : tokens.isError ? (
        <ErrorState error={tokens.error} onRetry={() => void tokens.refetch()} />
      ) : tokens.data.length === 0 ? (
        <EmptyState icon={KeyIcon} title="No agent tokens" className="py-6 sm:py-6">
          Each server running the OptiServe agent uses a token to send its numbers. Create one above.
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line/70">
          {tokens.data.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
              <div>
                <p className="font-medium text-ink">{t.label}</p>
                <p className="text-sm text-muted">
                  Created {timeAgo(t.created_at)} ·{" "}
                  {t.last_used_at ? `last used ${timeAgo(t.last_used_at)}${t.server_name ? ` by ${t.server_name}` : ""}` : "never used"}
                </p>
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

// ---------- how OptiServe acts ----------

/** Same scale as the backend: risk 0 → 85% busy target, risk 1 → 55%. */
export function targetPct(risk: number): number {
  return Math.round((0.85 + (0.55 - 0.85) * Math.min(Math.max(risk, 0), 1)) * 100);
}

/** The one-line explanation under the slider. */
export function riskSentence(risk: number): string {
  const t = targetPct(risk);
  if (risk < 0.35) return `Servers run up to ${t}% busy: fewer servers and lower bills, less room for sudden spikes.`;
  if (risk > 0.65) return `Servers run up to ${t}% busy: plenty of spare room for spikes, at a higher cost.`;
  return `Servers run up to ${t}% busy: a balance of savings and spare room.`;
}

function Switch({
  label,
  checked,
  onChange,
  busy,
  children,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
  busy?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="min-w-0 text-sm">
        <p className="font-medium text-ink">{label}</p>
        <div className="mt-0.5 text-ink-soft">{children}</div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        disabled={busy}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors duration-150 disabled:opacity-60",
          checked ? "bg-accent" : "bg-slate-500",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow transition-transform duration-150",
            checked && "translate-x-5",
          )}
        />
      </button>
    </div>
  );
}

function Warning({ children }: { children: ReactNode }) {
  return (
    <p className="mt-2 flex gap-2 rounded-xl bg-warn-soft px-3 py-2 text-sm text-ink-soft" role="note">
      <WarningIcon className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

function ActsForm({ s }: { s: AppSettings }) {
  const update = useUpdateSettings();
  const toast = useToast();
  const [risk, setRisk] = useState(s.risk);
  const [confirmReal, setConfirmReal] = useState(false);
  const save = (body: Parameters<typeof update.mutate>[0], done: string) =>
    update.mutate(body, { onSuccess: () => toast.show(done, "success"), onError: (e) => toast.show(e.message, "error") });

  return (
    <div className="space-y-6">
      <div>
        <label htmlFor="risk" className="text-sm font-medium text-ink">
          How careful should OptiServe be?
        </label>
        <div className="mt-3 flex items-center gap-3 text-xs font-medium text-muted">
          <span className="shrink-0">Save more</span>
          <input
            id="risk"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={risk}
            onChange={(e) => setRisk(Number(e.target.value))}
            className="h-2 w-full cursor-pointer accent-[var(--color-accent)]"
            aria-valuetext={riskSentence(risk)}
          />
          <span className="shrink-0">Stay safe</span>
        </div>
        <p className="mt-2 text-sm text-ink-soft">{riskSentence(risk)}</p>
        {risk !== s.risk && (
          <div className="mt-3 flex gap-2">
            <Button size="sm" loading={update.isPending} onClick={() => save({ risk }, "Saved. Suggestions use it from the next minute.")}>
              Save change
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setRisk(s.risk)}>
              Undo
            </Button>
          </div>
        )}
      </div>

      <div className="border-t border-line/70 pt-5">
        <Switch
          label="Live mode"
          checked={s.live_mode}
          busy={update.isPending}
          onChange={(v) => save({ live_mode: v }, v ? "Live mode is on." : "Live mode is off.")}
        >
          Looks at minutes of data instead of days, so OptiServe reacts quickly. Same real numbers.
        </Switch>
        {s.live_mode && (
          <Warning>For demos: suggestions come within minutes and can change often. Turn it off for everyday use.</Warning>
        )}
      </div>

      <div className="border-t border-line/70 pt-5">
        <Switch
          label="Dry run (practice)"
          checked={s.dry_run}
          busy={update.isPending}
          onChange={(v) => (v ? save({ dry_run: true }, "Dry run is on. Nothing will change in AWS.") : setConfirmReal(true))}
        >
          {s.dry_run
            ? "Dry run is on. Approved changes are logged, but nothing changes in AWS."
            : "Dry run is off. Approved changes really happen in AWS."}
        </Switch>
        {confirmReal && (
          <div className="mt-3 rounded-xl bg-danger-soft p-3 text-sm" role="alertdialog" aria-label="Turn off dry run?">
            <p className="text-ink-soft">
              After this, approving a suggestion really adds, removes or stops servers in AWS (only on groups tagged
              optiserve:managed=true). Nothing changes without your Approve.
            </p>
            <div className="mt-3 flex gap-2">
              <Button
                variant="danger"
                size="sm"
                loading={update.isPending}
                onClick={() => {
                  save({ dry_run: false }, "Dry run is off. Approved changes now happen in AWS.");
                  setConfirmReal(false);
                }}
              >
                Yes, make real changes
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setConfirmReal(false)}>
                Keep dry run
              </Button>
            </div>
          </div>
        )}
        {!s.dry_run && !confirmReal && <Warning>Approved changes are real. Each one is logged in Activity.</Warning>}
      </div>
      {s.updated_by && s.updated_at && (
        <p className="text-xs text-muted">
          Last changed by {s.updated_by} {timeAgo(s.updated_at)}.
        </p>
      )}
    </div>
  );
}

function Acts() {
  const settings = useAppSettings();
  return (
    <Card title="How OptiServe acts">
      {settings.isPending ? (
        <Skeleton lines={4} />
      ) : settings.isError ? (
        <ErrorState error={settings.error} onRetry={() => void settings.refetch()} />
      ) : (
        <ActsForm key={`${settings.data.risk}`} s={settings.data} />
      )}
    </Card>
  );
}

// ---------- prices ----------

function PriceRow({ r }: { r: ServerRow }) {
  const setPrice = useSetPrice();
  const toast = useToast();
  const [value, setValue] = useState(r.price_source === "override" && r.hourly_usd !== null ? String(r.hourly_usd) : "");
  const parsed = value.trim() === "" ? null : Number(value);
  const invalid = parsed !== null && (!Number.isFinite(parsed) || parsed < 0);
  const current = r.price_source === "override" ? r.hourly_usd : null;
  const changed = parsed !== current;

  return (
    <li className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <p className="truncate font-medium text-ink">{r.name}</p>
        <p className="text-xs text-muted">
          {r.instance_type ?? "Unknown type"} · default{" "}
          {r.table_hourly_usd === null ? "not in the price table" : `$${r.table_hourly_usd}/hour`}
          {r.monthly_cost_inr !== null && ` · ${formatInr(r.monthly_cost_inr)}/month now`}
        </p>
      </div>
      <form
        className="flex items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (invalid) return;
          setPrice.mutate(
            { id: r.id, hourlyUsd: parsed },
            {
              onSuccess: () => toast.show(parsed === null ? `${r.name} uses the default price.` : `Price saved for ${r.name}.`, "success"),
              onError: (err) => toast.show(err.message, "error"),
            },
          );
        }}
      >
        <span className="text-sm text-muted">$</span>
        <input
          className={cn(inputClass, "w-24 tabular", invalid && "border-danger")}
          inputMode="decimal"
          placeholder={r.table_hourly_usd === null ? "0.00" : String(r.table_hourly_usd)}
          aria-label={`Price per hour for ${r.name} in US dollars`}
          value={value}
          onChange={(e) => setValue(e.target.value)}
        />
        <span className="text-sm text-muted">/hour</span>
        <Button type="submit" size="sm" variant="secondary" disabled={!changed || invalid} loading={setPrice.isPending}>
          Save
        </Button>
      </form>
    </li>
  );
}

function Prices() {
  const servers = useServers();
  return (
    <Card title="Prices">
      <p className="-mt-2 mb-3 text-sm text-ink-soft">
        Savings use these hourly prices. Defaults come from a built-in table; check them against your AWS bill and set your
        own if they differ. Leave empty to use the default.
      </p>
      {servers.isPending ? (
        <Skeleton lines={3} />
      ) : servers.isError ? (
        <ErrorState error={servers.error} onRetry={() => void servers.refetch()} />
      ) : servers.data.length === 0 ? (
        <EmptyState icon={ServerIcon} title="No servers yet" className="py-6 sm:py-6">
          Prices can be set once servers are connected.
        </EmptyState>
      ) : (
        <ul className="divide-y divide-line/70">
          {servers.data.map((r) => (
            <PriceRow key={`${r.id}-${r.hourly_usd ?? "none"}`} r={r} />
          ))}
        </ul>
      )}
    </Card>
  );
}

export function Settings() {
  return (
    <div>
      <PageHeader title="Settings" sentence="Your connections, agent tokens, prices and how OptiServe acts." />
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="min-w-0 space-y-6">
          <Acts />
          <Prices />
        </div>
        <div className="min-w-0 space-y-6">
          <Connections />
          <AgentTokens />
        </div>
      </div>
    </div>
  );
}
