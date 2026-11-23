import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useLogin, useMe } from "../api/hooks";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Logo } from "../components/Layout";

const input =
  "h-11 w-full rounded-xl border border-line bg-white px-3.5 text-sm text-ink placeholder:text-slate-400 " +
  "focus:border-accent focus:ring-2 focus:ring-accent-ring/50 focus:outline-none";

function returnPath(state: unknown): string {
  if (state && typeof state === "object" && "from" in state && typeof state.from === "string" && state.from.startsWith("/")) {
    return state.from === "/login" ? "/" : state.from;
  }
  return "/";
}

export function Login() {
  const me = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const to = returnPath(location.state);

  if (me.data) return <Navigate to={to} replace />;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ email: email.trim(), password }, { onSuccess: () => navigate(to, { replace: true }) });
  };

  return (
    <div className="grid min-h-screen place-items-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo />
          <p className="text-ink-soft">Right-size your servers with a copilot you approve.</p>
        </div>
        <Card>
          <h1 className="mb-5 text-xl font-semibold">Sign in</h1>
          <form onSubmit={submit} className="space-y-4" noValidate>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink-soft">Email</span>
              <input
                className={input}
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium text-ink-soft">Password</span>
              <input
                className={input}
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {login.isError && (
              <p role="alert" className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger">
                {login.error.message}
              </p>
            )}
            <Button type="submit" size="lg" className="w-full" loading={login.isPending} disabled={!email || !password}>
              Sign in
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
