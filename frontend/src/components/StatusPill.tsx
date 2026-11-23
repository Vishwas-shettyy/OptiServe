import type { FleetStatus } from "../api/types";
import { Pill, type PillTone } from "./Pill";

const look: Record<FleetStatus, { label: string; tone: PillTone }> = {
  busy: { label: "Busy", tone: "warn" },
  normal: { label: "Normal", tone: "accent" },
  idle: { label: "Idle", tone: "neutral" },
  unhealthy: { label: "Unhealthy", tone: "danger" },
  stopped: { label: "Stopped", tone: "neutral" },
};

/** Busy / Normal / Idle / Unhealthy / Stopped. */
export function StatusPill({ status }: { status: FleetStatus }) {
  const l = look[status];
  return (
    <Pill tone={l.tone} dot>
      {l.label}
    </Pill>
  );
}

/** "OptiServe can change it" or "Suggestions only". */
export function ManagedPill({ managed }: { managed: boolean }) {
  return managed ? <Pill tone="good">Managed</Pill> : <Pill>Suggestions only</Pill>;
}
