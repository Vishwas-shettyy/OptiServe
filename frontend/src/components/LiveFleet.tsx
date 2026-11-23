// Live fleet: one breathing tile per server, grouped by group. Colour and breathing speed follow real CPU.
import type { CSSProperties } from "react";
import { Link } from "react-router-dom";
import type { FleetGroup, FleetServer } from "../api/types";
import { cn } from "../lib/cn";
import { formatInr, formatPct, plural } from "../lib/format";
import { WarningIcon } from "../lib/icons";
import { Pill } from "./Pill";

export type Load = "calm" | "warm" | "hot";

/** calm blue < 50% ≤ amber < 80% ≤ red. */
export function loadOf(cpu: number | null): Load {
  if (cpu === null || cpu < 50) return "calm";
  if (cpu < 80) return "warm";
  return "hot";
}

/** Busier servers breathe faster: 4.5 s when quiet down to 1.2 s at 100%. */
export function breathSeconds(cpu: number | null): number {
  const c = Math.min(Math.max(cpu ?? 0, 0), 100);
  return Math.round((4.5 - 3.3 * (c / 100)) * 10) / 10;
}

const loadStyle: Record<Load, { rgb: string; tile: string; text: string; word: string }> = {
  calm: { rgb: "59 130 246", tile: "border-blue-200 bg-blue-50", text: "text-blue-700", word: "calm" },
  warm: { rgb: "217 119 6", tile: "border-amber-200 bg-amber-50", text: "text-amber-700", word: "busy" },
  hot: { rgb: "220 38 38", tile: "border-red-200 bg-red-50", text: "text-red-700", word: "very busy" },
};

/** The plain words a tile is announced with. */
export function tileLabel(s: FleetServer): string {
  if (s.status === "stopped") return `${s.name}: stopped`;
  if (s.status === "unhealthy") return `${s.name}: needs attention. ${s.reason}`;
  if (s.status === "idle") return `${s.name}: asleep, almost no work`;
  return `${s.name}: ${formatPct(s.cpu_pct)} busy, ${loadStyle[loadOf(s.cpu_pct)].word}`;
}

function Tip({ s }: { s: FleetServer }) {
  return (
    <span
      role="tooltip"
      className={cn(
        "pointer-events-none absolute bottom-full left-1/2 z-20 mb-2 hidden w-52 -translate-x-1/2 rounded-xl border border-line bg-white p-3 sm:block",
        "text-left text-xs text-ink-soft opacity-0 shadow-[var(--shadow-lift)] transition-opacity duration-150",
        "group-hover:opacity-100 group-focus-visible:opacity-100",
      )}
    >
      <span className="block truncate text-sm font-semibold text-ink">{s.name}</span>
      {s.status === "stopped" ? (
        <span className="mt-1 block">Stopped: costs nothing while off.</span>
      ) : (
        <>
          <span className="mt-1 block">
            CPU <span className="font-medium text-ink">{formatPct(s.cpu_pct)}</span> busy
          </span>
          <span className="block">
            Memory{" "}
            {s.mem_pct === null ? (
              <span className="text-muted">only with the agent</span>
            ) : (
              <span className="font-medium text-ink">{formatPct(s.mem_pct)}</span>
            )}
          </span>
          <span className="block">
            Cost{" "}
            {s.monthly_cost_inr === null ? (
              <span className="text-muted">price not set</span>
            ) : (
              <span className="font-medium text-ink">{formatInr(s.monthly_cost_inr)}/month</span>
            )}
          </span>
        </>
      )}
      <span className="mt-1.5 block text-muted">{s.reason}</span>
    </span>
  );
}

export function FleetTile({ s }: { s: FleetServer }) {
  const load = loadStyle[loadOf(s.cpu_pct)];
  const asleep = s.status === "idle";
  const stopped = s.status === "stopped";
  const sick = s.status === "unhealthy";
  const breathing = !asleep && !stopped;
  const style = { "--tile-rgb": load.rgb, "--breathe-s": `${breathSeconds(s.cpu_pct)}s` } as CSSProperties;

  return (
    <Link
      to={`/servers/${s.id}`}
      aria-label={tileLabel(s)}
      className="group relative flex w-[4.75rem] flex-col items-center gap-1.5 rounded-2xl focus-visible:outline-offset-4"
      data-status={s.status}
    >
      <span
        style={style}
        className={cn(
          "relative grid size-16 place-items-center rounded-2xl border-2 transition-colors duration-200",
          stopped
            ? "border-dashed border-slate-300 bg-slate-50 text-slate-400"
            : asleep
              ? "border-slate-200 bg-slate-100 text-slate-400 opacity-60"
              : cn(load.tile, load.text),
          sick && "border-danger ring-2 ring-danger/30",
          breathing && "breathe",
        )}
      >
        {stopped ? (
          <span className="text-[11px] font-medium">Off</span>
        ) : asleep ? (
          <span className="font-display text-sm font-semibold italic tracking-wider" aria-hidden>
            zZ
          </span>
        ) : (
          <span className="font-display text-base font-semibold tabular">{formatPct(s.cpu_pct)}</span>
        )}
        {sick && (
          <span className="absolute -top-2 -right-2 grid size-5 place-items-center rounded-full bg-danger text-white">
            <WarningIcon className="size-3" aria-hidden />
          </span>
        )}
      </span>
      <span className={cn("w-full truncate text-center text-xs", asleep || stopped ? "text-muted" : "text-ink-soft")}>
        {s.name}
      </span>
      <Tip s={s} />
    </Link>
  );
}

function Legend() {
  const items: { label: string; swatch: string }[] = [
    { label: "Calm", swatch: "bg-blue-400" },
    { label: "Busy", swatch: "bg-amber-500" },
    { label: "Very busy", swatch: "bg-red-500" },
    { label: "Asleep (idle)", swatch: "bg-slate-300" },
  ];
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted" aria-label="Colour key">
      {items.map((i) => (
        <li key={i.label} className="inline-flex items-center gap-1.5">
          <span className={cn("size-2.5 rounded-full", i.swatch)} aria-hidden />
          {i.label}
        </li>
      ))}
      <li className="inline-flex items-center gap-1.5">
        <span className="size-2.5 rounded-full ring-2 ring-danger" aria-hidden />
        Needs attention
      </li>
    </ul>
  );
}

export function LiveFleet({ groups }: { groups: FleetGroup[] }) {
  return (
    <div className="space-y-5">
      {groups.map((g) => (
        <section key={g.id} aria-label={`Group ${g.name}`}>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold text-ink">{g.name}</h3>
            <span className="text-xs text-muted">{plural(g.servers.length, "server")}</span>
            {g.provider === "aws" &&
              (g.managed ? <Pill tone="good">OptiServe can change it</Pill> : <Pill>Suggestions only</Pill>)}
          </div>
          <ul className="flex flex-wrap gap-3">
            {g.servers.map((s) => (
              <li key={s.id}>
                <FleetTile s={s} />
              </li>
            ))}
          </ul>
        </section>
      ))}
      <Legend />
    </div>
  );
}
