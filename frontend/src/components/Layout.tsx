import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useHealth, useLogout, useMe } from "../api/hooks";
import { cn } from "../lib/cn";
import { ChevronDownIcon, LogOutIcon, UserIcon } from "../lib/icons";
import { Pill } from "./Pill";
import { useToast } from "./Toast";

const NAV = [
  { to: "/", label: "Home", end: true },
  { to: "/servers", label: "Servers", end: false },
  { to: "/activity", label: "Activity", end: false },
  { to: "/settings", label: "Settings", end: false },
] as const;

export function Logo() {
  return (
    <span className="flex items-center gap-2">
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="9" fill="#2563EB" />
        <path d="M9 20.5a7 7 0 1 1 14 0" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
        <circle cx="16" cy="20.5" r="2.5" fill="#fff" />
      </svg>
      <span className="font-display text-lg font-semibold tracking-tight text-ink">OptiServe</span>
    </span>
  );
}

function UserMenu() {
  const me = useMe();
  const logout = useLogout();
  const navigate = useNavigate();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const signOut = () => {
    logout.mutate(undefined, {
      onSettled: () => {
        navigate("/login", { replace: true });
        toast.show("You are signed out.");
      },
    });
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-1.5 rounded-xl px-2 py-1.5 text-sm text-ink-soft hover:bg-slate-100"
      >
        <span className="grid size-7 place-items-center rounded-full bg-accent-soft text-accent">
          <UserIcon className="size-4" aria-hidden />
        </span>
        <span className="sr-only">Account</span>
        <ChevronDownIcon className="size-4" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="glass absolute right-0 mt-2 w-60 rounded-2xl p-2 shadow-[var(--shadow-lift)]">
          <p className="truncate px-3 py-2 text-xs text-muted">Signed in as {me.data?.email}</p>
          <button
            type="button"
            role="menuitem"
            onClick={signOut}
            className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left text-sm text-ink hover:bg-slate-100"
          >
            <LogOutIcon className="size-4" aria-hidden /> Sign out
          </button>
        </div>
      )}
    </div>
  );
}

function NavItems({ className }: { className?: string }) {
  return (
    <nav aria-label="Main" className={className}>
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            cn(
              "whitespace-nowrap rounded-xl px-3 py-1.5 text-sm font-medium transition-colors",
              isActive ? "bg-accent-soft text-accent" : "text-ink-soft hover:bg-slate-100 hover:text-ink",
            )
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

/** Glass top bar (logo, nav, live-mode badge, user menu) above the page. */
export function Layout() {
  const health = useHealth();
  return (
    <div className="min-h-screen">
      <header className="glass sticky top-0 z-40 border-x-0 border-t-0 border-b-line/70">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4 sm:px-6">
          <NavLink to="/" aria-label="OptiServe home">
            <Logo />
          </NavLink>
          <NavItems className="ml-4 hidden items-center gap-1 md:flex" />
          <div className="ml-auto flex items-center gap-2">
            {health.data?.live_mode && (
              <Pill tone="accent" dot className="animate-pulse motion-reduce:animate-none" >
                Live mode
              </Pill>
            )}
            {health.data?.dry_run && <Pill tone="neutral">Dry run</Pill>}
            <UserMenu />
          </div>
        </div>
        <NavItems className="flex gap-1 overflow-x-auto px-4 pb-2 md:hidden" />
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}
