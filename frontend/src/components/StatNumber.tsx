import type { ReactNode } from "react";
import { cn } from "../lib/cn";

type Tone = "default" | "accent" | "good" | "warn" | "danger";

interface StatNumberProps {
  /** The number, already formatted (e.g. "₹4,200" or "23%"). */
  value: ReactNode;
  /** The word that says what the number means — required, so no number stands alone. */
  label: string;
  /** Optional extra line in plain words. */
  hint?: ReactNode;
  tone?: Tone;
  size?: "md" | "lg";
  className?: string;
}

const toneClass: Record<Tone, string> = {
  default: "text-ink",
  accent: "text-accent",
  good: "text-good",
  warn: "text-warn",
  danger: "text-danger",
};

/** A number with the word next to it ("23% busy"). */
export function StatNumber({ value, label, hint, tone = "default", size = "md", className }: StatNumberProps) {
  return (
    <div className={cn("min-w-0", className)}>
      <p className="flex flex-wrap items-baseline gap-x-2">
        <span
          className={cn(
            "font-display font-semibold tabular leading-none",
            size === "lg" ? "text-4xl sm:text-5xl" : "text-2xl sm:text-3xl",
            toneClass[tone],
          )}
        >
          {value}
        </span>
        <span className="text-sm font-medium text-muted">{label}</span>
      </p>
      {hint && <p className="mt-1.5 text-sm text-muted">{hint}</p>}
    </div>
  );
}
