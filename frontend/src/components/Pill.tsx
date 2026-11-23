import type { ReactNode } from "react";
import { cn } from "../lib/cn";

export type PillTone = "neutral" | "accent" | "good" | "warn" | "danger";

const tones: Record<PillTone, string> = {
  neutral: "bg-slate-100 text-ink-soft",
  accent: "bg-accent-soft text-accent",
  good: "bg-good-soft text-good",
  warn: "bg-warn-soft text-warn",
  danger: "bg-danger-soft text-danger",
};

interface PillProps {
  tone?: PillTone;
  icon?: ReactNode;
  /** Show a small dot (used for live status). */
  dot?: boolean;
  className?: string;
  children: ReactNode;
}

/** A small rounded status label ("Live mode", "Dry run", "Done"). */
export function Pill({ tone = "neutral", icon, dot = false, className, children }: PillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {icon}
      {children}
    </span>
  );
}
