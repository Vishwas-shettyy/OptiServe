import { cn } from "../lib/cn";
import { ErrorIcon, RetryIcon } from "../lib/icons";
import { Button } from "./Button";

interface ErrorStateProps {
  /** The error (its message is shown when it is plain words from the backend). */
  error?: unknown;
  title?: string;
  /** What the user can do about it. */
  hint?: string;
  onRetry?: () => void;
  className?: string;
}

function messageOf(error: unknown): string | null {
  if (error instanceof Error && error.message) return error.message;
  return null;
}

/** Something went wrong: say what, and what to do next. */
export function ErrorState({
  error,
  title = "Couldn't load this",
  hint = "Check that the OptiServe backend is running, then try again.",
  onRetry,
  className,
}: ErrorStateProps) {
  const message = messageOf(error);
  return (
    <div role="alert" className={cn("flex flex-col items-center px-4 py-10 text-center", className)}>
      <span className="mb-4 grid size-12 place-items-center rounded-2xl bg-danger-soft text-danger">
        <ErrorIcon className="size-6" aria-hidden strokeWidth={1.75} />
      </span>
      <h3 className="text-lg font-semibold">{title}</h3>
      {message && <p className="mt-2 max-w-md text-sm text-ink-soft">{message}</p>}
      <p className="mt-1 max-w-md text-sm text-muted">{hint}</p>
      {onRetry && (
        <Button variant="secondary" className="mt-5" icon={<RetryIcon className="size-4" aria-hidden />} onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
