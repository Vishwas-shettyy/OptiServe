// Capacity weather: the forecast as a strip of sun / cloud / storm icons with time labels.
import type { Weather, WeatherKind, WeatherSlot } from "../api/types";
import { cn } from "../lib/cn";
import { formatClock } from "../lib/format";
import { CloudIcon, StormIcon, SunIcon, type LucideIcon } from "../lib/icons";

const kinds: Record<WeatherKind, { icon: LucideIcon; word: string; className: string }> = {
  sun: { icon: SunIcon, word: "quiet", className: "bg-amber-50 text-amber-500" },
  cloud: { icon: CloudIcon, word: "normal", className: "bg-slate-100 text-slate-500" },
  storm: { icon: StormIcon, word: "peak", className: "bg-red-50 text-red-600" },
};

/** One line: "Storm expected at 18:00." / "Quiet ahead: no storms in the next 24 h." */
export function weatherSummary(w: Weather, clock: (iso: string) => string = formatClock): string {
  const storm = w.slots.find((s) => s.kind === "storm");
  if (storm) {
    const first = w.slots[0];
    return storm === first ? "Storm now: your servers are expected to be very busy." : `Storm expected at ${clock(storm.start)}.`;
  }
  if (w.slots.every((s) => s.kind === "sun")) return `Quiet ahead: no storms in the next ${w.horizon}.`;
  return `Normal load ahead: no storms in the next ${w.horizon}.`;
}

function Slot({ slot }: { slot: WeatherSlot }) {
  const k = kinds[slot.kind];
  const Icon = k.icon;
  const time = formatClock(slot.start);
  return (
    <li className="flex flex-col items-center gap-1.5" aria-label={`${time}: ${k.word}`} data-kind={slot.kind}>
      <span className={cn("grid size-10 place-items-center rounded-xl", k.className)}>
        <Icon className="size-5" aria-hidden strokeWidth={1.75} />
      </span>
      <span className="text-[11px] text-muted tabular">{time}</span>
    </li>
  );
}

export function CapacityWeather({ weather }: { weather: Weather }) {
  return (
    <div>
      <p className="font-display text-lg font-semibold text-ink">{weatherSummary(weather)}</p>
      <ol className="mt-4 grid grid-cols-6 gap-x-2 gap-y-4 sm:grid-cols-12">
        {weather.slots.map((s) => (
          <Slot key={s.start} slot={s} />
        ))}
      </ol>
      {weather.status === "learning" && <p className="mt-4 text-xs text-muted">{weather.message}</p>}
    </div>
  );
}
