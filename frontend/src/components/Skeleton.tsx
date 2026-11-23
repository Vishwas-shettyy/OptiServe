import { cn } from "../lib/cn";

interface SkeletonProps {
  className?: string;
  /** Number of stacked text lines to draw instead of one block. */
  lines?: number;
}

/** Shimmering placeholder shown while data loads. It never looks like real data. */
export function Skeleton({ className, lines }: SkeletonProps) {
  const bar = "animate-shimmer rounded-lg bg-[linear-gradient(90deg,#eef2f7_25%,#f8fafc_50%,#eef2f7_75%)] bg-[length:200%_100%]";
  if (lines) {
    return (
      <div className={cn("space-y-2.5", className)} role="status" aria-label="Loading">
        {Array.from({ length: lines }, (_, i) => (
          <div key={i} className={cn(bar, "h-3.5", i === lines - 1 ? "w-2/3" : "w-full")} />
        ))}
      </div>
    );
  }
  return <div className={cn(bar, "h-4 w-full", className)} role="status" aria-label="Loading" />;
}

/** A card-shaped loading block. */
export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={cn("glass rounded-[var(--radius-card)] p-6 shadow-[var(--shadow-card)]", className)}>
      <Skeleton className="mb-5 h-5 w-1/3" />
      <Skeleton lines={3} />
    </div>
  );
}
