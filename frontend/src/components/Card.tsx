import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "../lib/cn";

interface CardProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  /** Small heading above the content. */
  title?: ReactNode;
  /** Right side of the heading row (e.g. "Updated 3 s ago" or a button). */
  action?: ReactNode;
  as?: "section" | "div" | "article";
  padded?: boolean;
}

/** White glass card with a soft shadow — the base surface of every page. */
export function Card({ title, action, as: Tag = "section", padded = true, className, children, ...rest }: CardProps) {
  return (
    <Tag
      className={cn("glass rounded-[var(--radius-card)] shadow-[var(--shadow-card)]", padded && "p-5 sm:p-6", className)}
      {...rest}
    >
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-3">
          {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
          {action && <div className="shrink-0 text-sm text-muted">{action}</div>}
        </header>
      )}
      {children}
    </Tag>
  );
}
