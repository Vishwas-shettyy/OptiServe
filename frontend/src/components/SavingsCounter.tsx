// Animated counter of real rupees saved (realized savings from approved actions only).
import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { formatInr } from "../lib/format";

export function SavingsCounter({ value }: { value: number }) {
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(reduce ? value : 0);
  const from = useRef(reduce ? value : 0);

  useEffect(() => {
    const controls = animate(from.current, value, {
      duration: reduce ? 0 : 0.25,
      ease: "easeOut",
      onUpdate: (v) => {
        from.current = v;
        setShown(v);
      },
    });
    return () => controls.stop();
  }, [value, reduce]);

  return (
    <div className="rounded-2xl border border-good/20 bg-good-soft/70 px-4 py-3">
      <p className="flex items-baseline gap-2">
        <span className="font-display text-3xl font-semibold text-good tabular" data-testid="savings-counter">
          {formatInr(shown, { precise: true })}
        </span>
        <span className="text-sm font-medium text-muted">saved so far</span>
      </p>
      <p className="mt-0.5 text-xs text-muted">Real savings from changes you approved</p>
    </div>
  );
}
