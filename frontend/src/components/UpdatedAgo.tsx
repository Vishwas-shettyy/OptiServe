import { useEffect, useState } from "react";
import { timeAgo } from "../lib/format";

/** "Updated 3 s ago", ticking every second. `at` is a ms timestamp (react-query's dataUpdatedAt). */
export function UpdatedAgo({ at }: { at: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(id);
  }, []);
  if (!at) return null;
  return <span className="text-xs text-muted tabular">Updated {timeAgo(at, now)}</span>;
}
