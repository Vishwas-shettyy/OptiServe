// Onboarding: connect the first server, either by installing the agent or by connecting an AWS account.
import { useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAgentTokens, useConnectAws, useCreateAgentToken, useTestAws } from "../api/hooks";
import type { AgentTokenCreated, AwsConnectBody, AwsConnectResponse, AwsTestResponse } from "../api/types";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { PageHeader } from "../components/PageHeader";
import { Pill } from "../components/Pill";
import { StatNumber } from "../components/StatNumber";
import { cn } from "../lib/cn";
import { plural } from "../lib/format";
import {
  BackIcon,
  CheckIcon,
  ChevronDownIcon,
  CloudIcon,
  CopyIcon,
  DoneIcon,
  InfoIcon,
  NextIcon,
  ServerIcon,
  ShieldIcon,
  TerminalIcon,
  WarningIcon,
  type LucideIcon,
} from "../lib/icons";

/** The one-line installer (agent/install.sh). */
export const INSTALL_SCRIPT_URL = "https://raw.githubusercontent.com/Vishwas-shettyy/OptiServe/v2/agent/install.sh";
/** How often the page asks whether the new agent has reported yet. */
export const WAIT_POLL_MS = 2_000;
/** After this long without a report, show tips for finding the problem. */
const HELP_AFTER_S = 90;

export const AWS_REGIONS: { id: string; label: string }[] = [
  { id: "ap-south-1", label: "Asia Pacific (Mumbai)" },
  { id: "ap-south-2", label: "Asia Pacific (Hyderabad)" },
  { id: "ap-southeast-1", label: "Asia Pacific (Singapore)" },
  { id: "ap-southeast-2", label: "Asia Pacific (Sydney)" },
  { id: "ap-northeast-1", label: "Asia Pacific (Tokyo)" },
  { id: "us-east-1", label: "US East (N. Virginia)" },
  { id: "us-east-2", label: "US East (Ohio)" },
  { id: "us-west-2", label: "US West (Oregon)" },
  { id: "eu-west-1", label: "Europe (Ireland)" },
  { id: "eu-central-1", label: "Europe (Frankfurt)" },
];

/** The command a user pastes on their server. */
export function installCommand(backendUrl: string, token: string): string {
  const url = backendUrl.trim().replace(/\/+$/, "");
  return `curl -fsSL ${INSTALL_SCRIPT_URL} | sudo bash -s -- ${url} ${token}`;
}

/** True when the address only works on this computer, so a remote server could not reach it. */
export function isLocalAddress(url: string): boolean {
  try {
    const host = new URL(url).hostname;
    return host === "localhost" || host === "::1" || host === "[::1]" || host.startsWith("127.");
  } catch {
    return false;
  }
}

/** Seconds since `active` became true (real clock, resets when it turns off). */
function useElapsed(active: boolean): number {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!active) return;
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => {
      window.clearInterval(timer);
      setSeconds(0);
    };
  }, [active]);
  return active ? seconds : 0;
}

function formatElapsed(s: number): string {
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// ---------- shared pieces ----------

function ChoiceCard({
  icon: Icon,
  title,
  points,
  onClick,
}: {
  icon: LucideIcon;
  title: string;
  points: string[];
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "glass group flex h-full flex-col rounded-[var(--radius-card)] p-6 text-left shadow-[var(--shadow-card)] sm:p-8",
        "transition-[box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:shadow-[var(--shadow-lift)]",
      )}
    >
      <span className="mb-5 grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent">
        <Icon className="size-7" aria-hidden strokeWidth={1.75} />
      </span>
      <span className="font-display text-xl font-semibold text-ink sm:text-2xl">{title}</span>
      <ul className="mt-3 flex-1 space-y-2 text-sm leading-relaxed text-ink-soft">
        {points.map((p) => (
          <li key={p} className="flex gap-2">
            <CheckIcon className="mt-0.5 size-4 shrink-0 text-good" aria-hidden />
            {p}
          </li>
        ))}
      </ul>
      <span className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-accent">
        Start
        <NextIcon className="size-4 transition-transform duration-200 group-hover:translate-x-0.5" aria-hidden />
      </span>
    </button>
  );
}

function Step({ n, title, done, children }: { n: number; title: string; done?: boolean; children?: ReactNode }) {
  return (
    <li className="relative flex gap-4">
      <span
        className={cn(
          "grid size-8 shrink-0 place-items-center rounded-full text-sm font-semibold",
          done ? "bg-good-soft text-good" : "bg-accent-soft text-accent",
        )}
        aria-hidden
      >
        {done ? <CheckIcon className="size-4" /> : n}
      </span>
      <div className="min-w-0 flex-1 pb-6">
        <h3 className="pt-1 text-base font-semibold">{title}</h3>
        {children && <div className="mt-3">{children}</div>}
      </div>
    </li>
  );
}

function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div>
      <label className="block">
        <span className="text-sm font-medium text-ink">{label}</span>
        <span className="mt-1.5 block">{children}</span>
      </label>
      {hint && <span className="mt-1.5 block text-xs text-muted">{hint}</span>}
    </div>
  );
}

const inputClass =
  "h-10 w-full rounded-xl border border-line bg-white px-3 text-sm text-ink outline-none transition-colors " +
  "focus:border-accent focus:ring-2 focus:ring-accent-ring/50";

function Alert({ tone = "danger", children }: { tone?: "danger" | "warn" | "info"; children: ReactNode }) {
  const style = {
    danger: "bg-danger-soft text-danger",
    warn: "bg-warn-soft text-warn",
    info: "bg-accent-soft text-accent",
  }[tone];
  const Icon = tone === "info" ? InfoIcon : WarningIcon;
  return (
    <div role={tone === "danger" ? "alert" : "note"} className={cn("flex gap-2.5 rounded-xl px-3.5 py-3 text-sm", style)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="text-ink-soft">{children}</div>
    </div>
  );
}

function CopyBox({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const t = window.setTimeout(() => setCopied(false), 2_000);
    return () => window.clearTimeout(t);
  }, [copied]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900">
      <div className="flex items-center justify-between gap-2 border-b border-white/10 px-3 py-1.5">
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-400">
          <TerminalIcon className="size-3.5" aria-hidden />
          {label}
        </span>
        <button
          type="button"
          onClick={() => void copy()}
          className="inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-slate-200 hover:bg-white/10"
        >
          {copied ? <CheckIcon className="size-3.5 text-emerald-400" aria-hidden /> : <CopyIcon className="size-3.5" aria-hidden />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="overflow-x-auto px-4 py-3 text-[13px] leading-relaxed text-slate-100">
        <code data-testid="install-command">{text}</code>
      </pre>
    </div>
  );
}

function Success({ title, children, action }: { title: string; children: ReactNode; action: ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <div className="flex flex-col items-center px-4 py-8 text-center" role="status">
      <motion.span
        initial={reduce ? false : { scale: 0.4, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 420, damping: 18, duration: 0.25 }}
        className="relative mb-5 grid size-20 place-items-center rounded-full bg-good-soft text-good"
      >
        {!reduce && (
          <motion.span
            className="absolute inset-0 rounded-full border-2 border-good"
            initial={{ scale: 1, opacity: 0.6 }}
            animate={{ scale: 1.5, opacity: 0 }}
            transition={{ duration: 0.25, delay: 0.1 }}
            aria-hidden
          />
        )}
        <DoneIcon className="size-10" aria-hidden strokeWidth={1.75} />
      </motion.span>
      <motion.div
        initial={reduce ? false : { y: 8, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.25, delay: 0.05 }}
      >
        <h2 className="text-2xl font-semibold">{title}</h2>
        <div className="mx-auto mt-2 max-w-md text-ink-soft">{children}</div>
        <div className="mt-6 flex justify-center">{action}</div>
      </motion.div>
    </div>
  );
}

function GoHome() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  return (
    <Button
      size="lg"
      icon={<NextIcon className="size-5" aria-hidden />}
      onClick={() => {
        void qc.invalidateQueries();
        navigate("/");
      }}
    >
      Go to Home
    </Button>
  );
}

function Waiting({ label, seconds }: { label: string; seconds: number }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-accent/20 bg-accent-soft/60 px-4 py-3" role="status">
      <span className="relative flex size-3" aria-hidden>
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-60" />
        <span className="relative inline-flex size-3 rounded-full bg-accent" />
      </span>
      <span className="flex-1 text-sm font-medium text-ink">{label}</span>
      <span className="tabular text-xs text-muted">{formatElapsed(seconds)}</span>
    </div>
  );
}

// ---------- (a) install the agent ----------

function AgentFlow() {
  const create = useCreateAgentToken();
  const [label, setLabel] = useState("my-server");
  const [token, setToken] = useState<AgentTokenCreated | null>(null);
  const [backendUrl, setBackendUrl] = useState(() => window.location.origin);
  const tokens = useAgentTokens({ poll: token ? WAIT_POLL_MS : 0 });
  const reported = token ? tokens.data?.find((t) => t.id === token.id && t.last_used_at !== null) : undefined;
  const seconds = useElapsed(token !== null && !reported);

  if (token && reported) {
    return (
      <Success title={`${reported.server_name ?? "Your server"} is connected`} action={<GoHome />}>
        Its first numbers just arrived. OptiServe gets a fresh reading every 10 seconds, so Home is already live.
      </Success>
    );
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate(label.trim() || "my-server", { onSuccess: setToken });
  }

  return (
    <ol>
      <Step n={1} title="Name this server" done={token !== null}>
        {token ? (
          <p className="text-sm text-ink-soft">
            Install key created for <span className="font-medium text-ink">{token.label}</span>.
          </p>
        ) : (
          <form onSubmit={submit} className="space-y-3">
            <Field label="Name" hint="Only for you, to tell install keys apart later in Settings.">
              <input className={inputClass} value={label} maxLength={100} onChange={(e) => setLabel(e.target.value)} />
            </Field>
            {create.isError && <Alert>{create.error.message}</Alert>}
            <Button type="submit" loading={create.isPending}>
              Create install command
            </Button>
          </form>
        )}
      </Step>
      {token && (
        <>
          <Step n={2} title="Run this on your server">
            <div className="space-y-3">
              <Field label="OptiServe address your server can reach">
                <input
                  className={inputClass}
                  value={backendUrl}
                  inputMode="url"
                  onChange={(e) => setBackendUrl(e.target.value)}
                />
              </Field>
              {isLocalAddress(backendUrl) && (
                <Alert tone="warn">
                  This address only works on this computer. If the server is somewhere else, type the address it can
                  reach, such as <span className="font-medium">http://203.0.113.10:8000</span>.
                </Alert>
              )}
              <CopyBox label="Terminal on your server" text={installCommand(backendUrl, token.token)} />
              <p className="text-xs text-muted">
                Works on Ubuntu 22.04+ and Amazon Linux 2023. The key inside is shown only once: copy it now. You can
                turn it off anytime in Settings.
              </p>
            </div>
          </Step>
          <Step n={3} title="Wait for the first numbers">
            <Waiting label="Waiting for your server…" seconds={seconds} />
            {tokens.isError && (
              <p className="mt-2 text-sm text-danger">Can't check right now: {tokens.error.message} Retrying…</p>
            )}
            {seconds >= HELP_AFTER_S && (
              <div className="mt-3">
                <Alert tone="info">
                  Not showing up yet? On the server, check the agent with{" "}
                  <code className="rounded bg-white/70 px-1">sudo systemctl status optiserve-agent</code> and its log
                  with <code className="rounded bg-white/70 px-1">sudo journalctl -u optiserve-agent -n 30</code>. The
                  server must be able to reach the address above.
                </Alert>
              </div>
            )}
          </Step>
        </>
      )}
    </ol>
  );
}

// ---------- (b) connect AWS ----------

function FoundList({ found }: { found: AwsTestResponse }) {
  const shown = found.instances.slice(0, 6);
  const more = found.instances.length - shown.length;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <StatNumber value={String(found.instances.length)} label={found.instances.length === 1 ? "server found" : "servers found"} />
        <StatNumber value={String(found.groups.length)} label={found.groups.length === 1 ? "auto scaling group" : "auto scaling groups"} />
      </div>
      {found.instances.length === 0 ? (
        <Alert tone="warn">No servers in this region. Pick the region your servers run in and test again.</Alert>
      ) : (
        <ul className="divide-y divide-line/70 rounded-xl border border-line/70 bg-white/70">
          {found.groups.map((g) => (
            <li key={`g-${g.name}`} className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm">
              <span className="font-medium text-ink">{g.name}</span>
              <span className="text-muted">group of {plural(g.desired, "server")}</span>
              <span className="ml-auto">
                {g.managed ? <Pill tone="good">OptiServe can change it</Pill> : <Pill>Suggestions only</Pill>}
              </span>
            </li>
          ))}
          {shown.map((i) => (
            <li key={i.instance_id} className="flex flex-wrap items-center gap-2 px-4 py-2.5 text-sm">
              <span className="font-medium text-ink">{i.name}</span>
              <span className="text-muted">{i.state === "running" ? "running" : i.state}</span>
              {i.group && <span className="text-muted">in {i.group}</span>}
            </li>
          ))}
          {more > 0 && <li className="px-4 py-2.5 text-sm text-muted">and {plural(more, "more server")}</li>}
        </ul>
      )}
      <p className="text-xs text-muted">
        AWS doesn't report memory on its own. Install the agent on a server too if you want memory numbers.
      </p>
    </div>
  );
}

function AwsFlow() {
  const test = useTestAws();
  const connect = useConnectAws();
  const [region, setRegion] = useState("ap-south-1");
  const [useKeys, setUseKeys] = useState(false);
  const [keyId, setKeyId] = useState("");
  const [secret, setSecret] = useState("");
  const [sessionToken, setSessionToken] = useState("");
  const [result, setResult] = useState<AwsConnectResponse | null>(null);
  const seconds = useElapsed(connect.isPending);

  const body: AwsConnectBody = useKeys
    ? {
        region,
        access_key_id: keyId.trim() || undefined,
        secret_access_key: secret.trim() || undefined,
        session_token: sessionToken.trim() || undefined,
      }
    : { region };

  /** Any change to what will be sent makes the last test result stale. */
  function changed<T>(set: (v: T) => void) {
    return (v: T) => {
      set(v);
      test.reset();
      connect.reset();
    };
  }

  if (result?.sync) {
    const s = result.sync;
    return (
      <Success title="AWS is connected" action={<GoHome />}>
        <span className="block">
          {plural(s.instances, "server")} and {plural(s.groups, "group")} found, with{" "}
          {plural(s.points_added, "reading")} of history brought in. OptiServe now checks AWS every few minutes.
        </span>
      </Success>
    );
  }

  const found = test.data;
  return (
    <ol>
      <Step n={1} title="Choose your AWS account" done={found !== undefined}>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            test.mutate(body);
          }}
        >
          <Field label="Region" hint="Where your servers run.">
            <select className={inputClass} value={region} onChange={(e) => changed(setRegion)(e.target.value)}>
              {AWS_REGIONS.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label} · {r.id}
                </option>
              ))}
            </select>
          </Field>

          <Alert tone="info">
            <span className="inline-flex items-center gap-1.5 font-medium text-ink">
              <ShieldIcon className="size-4" aria-hidden /> Best: no keys at all.
            </span>{" "}
            Run OptiServe on an EC2 server with an IAM role and leave the keys empty. OptiServe only reads your servers
            and changes nothing until you approve.
          </Alert>

          <div>
            <button
              type="button"
              aria-expanded={useKeys}
              onClick={() => changed(setUseKeys)(!useKeys)}
              className="inline-flex items-center gap-1.5 text-sm font-medium text-accent"
            >
              <ChevronDownIcon className={cn("size-4 transition-transform", useKeys && "rotate-180")} aria-hidden />
              Use access keys instead (optional)
            </button>
            {useKeys && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <Field label="Access key ID">
                  <input
                    className={inputClass}
                    value={keyId}
                    autoComplete="off"
                    spellCheck={false}
                    onChange={(e) => changed(setKeyId)(e.target.value)}
                  />
                </Field>
                <Field label="Secret access key">
                  <input
                    className={inputClass}
                    type="password"
                    value={secret}
                    autoComplete="off"
                    onChange={(e) => changed(setSecret)(e.target.value)}
                  />
                </Field>
                <div className="sm:col-span-2">
                  <Field label="Session token" hint="Only for temporary keys. Keys stay in memory and are never saved.">
                    <input
                      className={inputClass}
                      type="password"
                      value={sessionToken}
                      autoComplete="off"
                      onChange={(e) => changed(setSessionToken)(e.target.value)}
                    />
                  </Field>
                </div>
              </div>
            )}
          </div>

          {test.isError && <Alert>{test.error.message}</Alert>}
          <Button type="submit" variant={found ? "secondary" : "primary"} loading={test.isPending}>
            {found ? "Test again" : "Test connection"}
          </Button>
        </form>
      </Step>

      {found && (
        <Step n={2} title={`Here's what OptiServe can see in ${found.region}`}>
          <FoundList found={found} />
        </Step>
      )}

      {found && (
        <Step n={3} title="Bring in the last 14 days">
          {connect.isPending ? (
            <div className="space-y-3">
              <Waiting label="Bringing in 14 days of history from CloudWatch…" seconds={seconds} />
              <div className="h-1.5 animate-pulse rounded-full bg-accent/40" aria-hidden />
              <p className="text-xs text-muted">This usually takes under a minute. Keep this page open.</p>
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-ink-soft">
                OptiServe reads past busy-ness so its forecasts work from day one.
              </p>
              {connect.isError && <Alert>{connect.error.message}</Alert>}
              {result && !result.sync && (
                <Alert>
                  Connected, but the history could not be read:{" "}
                  {result.connection.error_message ?? "AWS did not answer."} Check the permissions in
                  demo/iam_policy.json, then try again.
                </Alert>
              )}
              <Button
                size="lg"
                onClick={() => connect.mutate(body, { onSuccess: setResult })}
                disabled={found.instances.length === 0}
              >
                Connect and bring in history
              </Button>
            </div>
          )}
        </Step>
      )}
    </ol>
  );
}

// ---------- page ----------

type Mode = "agent" | "aws";

const flows: Record<Mode, { icon: LucideIcon; title: string; sentence: string }> = {
  agent: {
    icon: ServerIcon,
    title: "Install the agent",
    sentence: "One command on your server. It shows up here within about 10 seconds.",
  },
  aws: {
    icon: CloudIcon,
    title: "Connect AWS",
    sentence: "Read-only. OptiServe finds your servers and groups and brings in their history.",
  },
};

export function Connect() {
  const [mode, setMode] = useState<Mode | null>(null);

  if (mode === null) {
    return (
      <div>
        <PageHeader
          title="Connect your first server"
          sentence="Pick how OptiServe should see your servers. Both use real numbers only, and take about 2 minutes."
        />
        <div className="grid gap-6 md:grid-cols-2">
          <ChoiceCard
            icon={ServerIcon}
            title="Install the agent"
            onClick={() => setMode("agent")}
            points={[
              "Any Linux server: any cloud or your own hardware",
              "Sends how busy it is every 10 seconds, memory included",
              "One copy-paste command",
            ]}
          />
          <ChoiceCard
            icon={CloudIcon}
            title="Connect AWS"
            onClick={() => setMode("aws")}
            points={[
              "Finds your EC2 servers and Auto Scaling groups",
              "Brings in the last 14 days so forecasts work right away",
              "Can add or stop servers, only when you approve",
            ]}
          />
        </div>
      </div>
    );
  }

  const flow = flows[mode];
  const Icon = flow.icon;
  return (
    <div className="mx-auto max-w-3xl">
      <Button variant="ghost" size="sm" className="-ml-3 mb-3" icon={<BackIcon className="size-4" aria-hidden />} onClick={() => setMode(null)}>
        Other ways to connect
      </Button>
      <Card>
        <header className="mb-6 flex items-start gap-4">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-accent-soft text-accent">
            <Icon className="size-6" aria-hidden strokeWidth={1.75} />
          </span>
          <div>
            <h1 className="text-2xl font-semibold">{flow.title}</h1>
            <p className="mt-1 text-ink-soft">{flow.sentence}</p>
          </div>
        </header>
        {mode === "agent" ? <AgentFlow /> : <AwsFlow />}
      </Card>
    </div>
  );
}
