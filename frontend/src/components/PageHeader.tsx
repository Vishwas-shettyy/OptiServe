import type { ReactNode } from "react";

/** Page title, one plain sentence under it, and an optional right-side slot. */
export function PageHeader({ title, sentence, aside }: { title: string; sentence?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold sm:text-3xl">{title}</h1>
        {sentence && <p className="mt-1 text-ink-soft">{sentence}</p>}
      </div>
      {aside}
    </div>
  );
}
