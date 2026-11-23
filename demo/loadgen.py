#!/usr/bin/env python3
"""Real HTTP load for the OptiServe demo: ramps up to a target rate, holds it, then ramps down.

Usage:
  python demo/loadgen.py --url http://<alb-or-instance> --rps 200 --minutes 8
  python demo/loadgen.py --url http://localhost:8000 --rps 20 --minutes 1 --ramp 10

--url may be the app's base URL (then /work?ms=<--work-ms> is called) or a full URL to hit as is.
Needs Python 3.9+ and httpx (pip install httpx). Stop early with Ctrl+C: it prints a summary either way.
"""

import argparse
import asyncio
import math
import signal
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple
from urllib.parse import urlsplit

import httpx

TICK_S = 0.05


@dataclass
class Plan:
    """Target request rate over time: linear ramp up, hold, linear ramp down."""

    rps: float
    total_s: float
    ramp_s: float

    def rate(self, t: float) -> float:
        """Return the target requests/second at `t` seconds after the start."""
        if t < 0 or t >= self.total_s:
            return 0.0
        ramp = min(self.ramp_s, self.total_s / 2)
        if ramp <= 0:
            return self.rps
        if t < ramp:
            return self.rps * t / ramp
        if t > self.total_s - ramp:
            return self.rps * (self.total_s - t) / ramp
        return self.rps

    def phase(self, t: float) -> str:
        """Return 'ramp up', 'hold' or 'ramp down' for the console."""
        ramp = min(self.ramp_s, self.total_s / 2)
        if t < ramp:
            return "ramp up"
        if t > self.total_s - ramp:
            return "ramp down"
        return "hold"


@dataclass
class Stats:
    """Running counters plus a one-second window of finished requests for the live line."""

    sent: int = 0
    ok: int = 0
    errors: int = 0
    dropped: int = 0  # not sent because too many were already in flight
    in_flight: int = 0
    latencies: List[float] = field(default_factory=list)
    recent: Deque[Tuple[float, float, bool]] = field(default_factory=deque)  # (finished_at, latency_ms, ok)

    def finish(self, latency_ms: float, ok: bool) -> None:
        """Record one finished request."""
        self.in_flight -= 1
        if ok:
            self.ok += 1
            self.latencies.append(latency_ms)
        else:
            self.errors += 1
        self.recent.append((time.monotonic(), latency_ms, ok))

    def window(self, seconds: float = 1.0) -> Tuple[float, Optional[float], Optional[float]]:
        """Return (completed per second, p50 ms, p95 ms) over the last `seconds`."""
        now = time.monotonic()
        while self.recent and now - self.recent[0][0] > seconds:
            self.recent.popleft()
        lat = sorted(l for _, l, ok in self.recent if ok)
        return len(self.recent) / seconds, percentile(lat, 50), percentile(lat, 95)


def percentile(sorted_values: List[float], p: float) -> Optional[float]:
    """Return the p-th percentile of already sorted values (nearest rank), or None."""
    if not sorted_values:
        return None
    k = max(0, min(len(sorted_values) - 1, math.ceil(p / 100 * len(sorted_values)) - 1))
    return sorted_values[k]


def target_url(url: str, work_ms: int) -> str:
    """Use the URL as given if it has a path; otherwise call the demo app's /work endpoint."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("--url must look like http://host[:port][/path]")
    if parts.path in ("", "/") and not parts.query:
        return f"{url.rstrip('/')}/work?ms={work_ms}"
    return url


def fmt_ms(v: Optional[float]) -> str:
    """Milliseconds for the console, or a dash."""
    return "   -" if v is None else f"{v:4.0f}"


async def one(client: httpx.AsyncClient, url: str, stats: Stats) -> None:
    """Send one request and record the outcome."""
    t0 = time.perf_counter()
    try:
        res = await client.get(url)
        ok = res.status_code < 400
    except httpx.HTTPError:
        ok = False
    stats.finish((time.perf_counter() - t0) * 1000, ok)


async def run(url: str, plan: Plan, max_in_flight: int, timeout_s: float, live: bool) -> Stats:
    """Send requests at the planned rate until the plan ends or Ctrl+C; return the stats."""
    stats = Stats()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, stop.set)
    except (NotImplementedError, RuntimeError):  # Windows
        pass
    limits = httpx.Limits(max_connections=max_in_flight, max_keepalive_connections=max_in_flight)
    tasks: set = set()
    start = time.monotonic()
    credit = 0.0
    last_print = 0.0
    async with httpx.AsyncClient(timeout=timeout_s, limits=limits) as client:
        while not stop.is_set():
            t = time.monotonic() - start
            if t >= plan.total_s:
                break
            credit += plan.rate(t) * TICK_S
            while credit >= 1.0:
                credit -= 1.0
                if stats.in_flight >= max_in_flight:
                    stats.dropped += 1
                    continue
                stats.sent += 1
                stats.in_flight += 1
                task = asyncio.create_task(one(client, url, stats))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            if t - last_print >= 1.0:
                last_print = t
                done_ps, p50, p95 = stats.window()
                line = (
                    f"{int(t) // 60:02d}:{int(t) % 60:02d}  {plan.phase(t):9s}  target {plan.rate(t):6.1f}/s  "
                    f"done {done_ps:6.1f}/s  p50 {fmt_ms(p50)} ms  p95 {fmt_ms(p95)} ms  "
                    f"in flight {stats.in_flight:4d}  errors {stats.errors}"
                )
                print(("\r" + line) if live else line, end="" if live else "\n", flush=True)
            await asyncio.sleep(TICK_S)
        if live:
            print()
        if tasks:
            print(f"Waiting for {len(tasks)} requests still in flight…", flush=True)
            await asyncio.wait(tasks, timeout=timeout_s)
    return stats


def summary(stats: Stats, elapsed_s: float) -> str:
    """Return the closing summary lines."""
    lat = sorted(stats.latencies)
    return "\n".join([
        f"Sent {stats.sent} requests in {elapsed_s:.0f} s ({stats.sent / max(elapsed_s, 1e-9):.1f}/s average).",
        f"OK {stats.ok}  ·  errors {stats.errors}  ·  skipped (too many in flight) {stats.dropped}",
        f"Latency p50 {fmt_ms(percentile(lat, 50))} ms  ·  p95 {fmt_ms(percentile(lat, 95))} ms  ·  "
        f"p99 {fmt_ms(percentile(lat, 99))} ms",
    ])


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Read the command line."""
    p = argparse.ArgumentParser(description="Real HTTP load with ramp up / hold / ramp down for the OptiServe demo.")
    p.add_argument("--url", required=True, help="demo app base URL (calls /work) or a full URL")
    p.add_argument("--rps", type=float, required=True, help="requests per second at the peak")
    p.add_argument("--minutes", type=float, required=True, help="total run time, ramps included")
    p.add_argument("--ramp", type=float, default=None, help="seconds to ramp up and down (default: 20%% of the run, max 120)")
    p.add_argument("--work-ms", type=int, default=50, help="CPU milliseconds per request when calling /work (default 50)")
    p.add_argument("--max-in-flight", type=int, default=500, help="cap on concurrent requests (default 500)")
    p.add_argument("--timeout", type=float, default=30.0, help="per-request timeout in seconds (default 30)")
    args = p.parse_args(argv)
    if args.rps <= 0 or args.minutes <= 0 or args.max_in_flight <= 0 or args.work_ms <= 0:
        p.error("--rps, --minutes, --work-ms and --max-in-flight must be positive")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point."""
    args = parse_args(argv)
    try:
        url = target_url(args.url, args.work_ms)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    total = args.minutes * 60
    ramp = args.ramp if args.ramp is not None else min(120.0, total * 0.2)
    plan = Plan(rps=args.rps, total_s=total, ramp_s=ramp)
    print(f"Load: {url}\nPeak {args.rps:g}/s for {args.minutes:g} min, ramping {ramp:.0f} s up and down. Ctrl+C stops.\n")
    started = time.monotonic()
    stats = asyncio.run(run(url, plan, args.max_in_flight, args.timeout, live=sys.stdout.isatty()))
    print("\n" + summary(stats, time.monotonic() - started))
    return 0 if stats.ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
