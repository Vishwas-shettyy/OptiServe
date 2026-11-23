import type { ReactNode } from "react";
import { cn } from "../lib/cn";
import type { LucideIcon } from "../lib/icons";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  /** What is missing and exactly how to get it. */
  children: ReactNode;
  /** The one obvious next step (usually a ButtonLink). */
  action?: ReactNode;
  className?: string;
}

/** Honest empty state: says why there is nothing and what to do. Never fills space with fake data. */
export function EmptyState({ icon: Icon, title, children, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center px-4 py-10 text-center sm:py-14", className)}>
      <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-accent-soft text-accent">
        <Icon className="size-6" aria-hidden strokeWidth={1.75} />
      </span>
      <h3 className="text-lg font-semibold">{title}</h3>
      <div className="mt-2 max-w-md text-sm leading-relaxed text-muted">{children}</div>
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}
