"""OptiServe demo app: a tiny real web app whose CPU use follows its traffic.

GET /             a small status page (also the load balancer health check)
GET /work?ms=50   burns about `ms` milliseconds of real CPU, spread over every core
GET /metrics      {"requests_per_min": n, ...} — read by the OptiServe agent (--requests-url)

Run: uvicorn app:app --host 0.0.0.0 --port 8000   (Python 3.9+, fastapi, uvicorn)
"""

import asyncio
import hashlib
import os
import socket
import threading
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from typing import AsyncIterator, Deque, Dict, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse

MAX_WORK_MS = 2_000
WINDOW_S = 60.0


class RequestCounter:
    """Counts requests in a sliding 60-second window (thread-safe)."""

    def __init__(self, window_s: float = WINDOW_S) -> None:
        """Create an empty counter."""
        self.window_s = window_s
        self.total = 0
        self._hits: Deque[float] = deque()
        self._lock = threading.Lock()

    def hit(self, now: Optional[float] = None) -> None:
        """Record one request."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self.total += 1
            self._hits.append(now)
            self._trim(now)

    def per_minute(self, now: Optional[float] = None) -> float:
        """Return requests in the last window, scaled to one minute."""
        now = time.monotonic() if now is None else now
        with self._lock:
            self._trim(now)
            return len(self._hits) * 60.0 / self.window_s

    def _trim(self, now: float) -> None:
        """Drop hits older than the window."""
        while self._hits and now - self._hits[0] > self.window_s:
            self._hits.popleft()


def burn(ms: int) -> int:
    """Do real CPU work (SHA-256 rounds) for about `ms` milliseconds; return the rounds done."""
    end = time.perf_counter() + ms / 1000.0
    digest = b"optiserve"
    rounds = 0
    while time.perf_counter() < end:
        for _ in range(200):
            digest = hashlib.sha256(digest).digest()
        rounds += 200
    return rounds


STATE: Dict[str, object] = {}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Start one worker process per core so /work can use every CPU (one Python thread can use only one)."""
    workers = int(os.environ.get("DEMO_WORKERS", "0")) or (os.cpu_count() or 1)
    pool = ProcessPoolExecutor(max_workers=workers)
    STATE["pool"] = pool
    STATE["workers"] = workers
    yield
    pool.shutdown(wait=False, cancel_futures=True)


app = FastAPI(title="OptiServe demo app", lifespan=lifespan)
counter = RequestCounter()
started = time.time()


@app.middleware("http")
async def count_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Count every request except the agent reading /metrics."""
    if request.url.path != "/metrics":
        counter.hit()
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """A small status page."""
    return (
        "<!doctype html><title>OptiServe demo app</title>"
        "<body style='font-family:system-ui;margin:3rem;color:#0f172a'>"
        f"<h1>OptiServe demo app</h1><p>Served by <b>{socket.gethostname()}</b>.</p>"
        f"<p>{counter.per_minute():.0f} requests in the last minute.</p>"
        "<p>Try <code>/work?ms=50</code> for real CPU work, or <code>/metrics</code>.</p></body>"
    )


@app.get("/work")
async def work(ms: int = Query(50, ge=1, le=MAX_WORK_MS)) -> Dict[str, object]:
    """Burn `ms` milliseconds of CPU in a worker process and say how long it took overall."""
    t0 = time.perf_counter()
    pool = STATE.get("pool")
    if isinstance(pool, ProcessPoolExecutor):
        rounds = await asyncio.get_running_loop().run_in_executor(pool, burn, ms)
    else:  # no lifespan (e.g. some test clients): work inline
        rounds = burn(ms)
    return {
        "host": socket.gethostname(),
        "work_ms": ms,
        "rounds": rounds,
        "took_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


@app.get("/metrics")
def metrics() -> Dict[str, object]:
    """Request counter for the OptiServe agent."""
    return {
        "requests_per_min": round(counter.per_minute(), 1),
        "requests_total": counter.total,
        "window_s": counter.window_s,
        "workers": STATE.get("workers"),
        "uptime_s": round(time.time() - started),
    }
