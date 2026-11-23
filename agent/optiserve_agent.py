#!/usr/bin/env python3
"""OptiServe agent: samples this machine every 10 s and sends the metrics to the OptiServe backend.

Python 3.9+. Dependencies: psutil, requests.
Usage: optiserve_agent.py --url https://optiserve.example.com --token osa_... [--requests-url http://127.0.0.1:8000/metrics]
Settings can also come from OPTISERVE_URL, OPTISERVE_TOKEN and OPTISERVE_REQUESTS_URL.
"""

import argparse
import logging
import os
import signal
import socket
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

import psutil
import requests

VERSION = "2.0.0"
IMDS = "http://169.254.169.254/latest"
BUFFER_WINDOW = timedelta(minutes=10)
MAX_BATCH = 60
BACKOFF_START_S = 10.0
BACKOFF_MAX_S = 300.0

log = logging.getLogger("optiserve-agent")


# ---------- identity ----------


def _imds_get(path: str, token: str) -> Optional[str]:
    """Read one IMDSv2 path; None if it is missing or unreachable."""
    try:
        res = requests.get(f"{IMDS}/{path}", headers={"X-aws-ec2-metadata-token": token}, timeout=1)
    except requests.RequestException:
        return None
    return res.text.strip() if res.status_code == 200 and res.text.strip() else None


def detect_identity() -> Dict[str, Optional[str]]:
    """Return host identity: EC2 instance details via IMDSv2 if available, else the hostname."""
    hostname = socket.gethostname()
    try:
        res = requests.put(
            f"{IMDS}/api/token", headers={"X-aws-ec2-metadata-token-ttl-seconds": "300"}, timeout=1
        )
        token = res.text.strip() if res.status_code == 200 else ""
    except requests.RequestException:
        token = ""
    if token:
        instance_id = _imds_get("meta-data/instance-id", token)
        if instance_id:
            return {
                "external_id": instance_id,
                "name": hostname,
                "instance_type": _imds_get("meta-data/instance-type", token),
                "region": _imds_get("meta-data/placement/region", token),
                # Present only when "instance metadata tags" is enabled on the instance.
                "asg_name": _imds_get("meta-data/tags/instance/aws:autoscaling:groupName", token),
            }
    return {"external_id": hostname, "name": hostname, "instance_type": None, "region": None, "asg_name": None}


# ---------- metrics ----------


class Collector:
    """Turns psutil counters into percentages and kbps rates between calls."""

    def __init__(self, requests_url: Optional[str]) -> None:
        """Prime the CPU and network counters so the first sample has a baseline."""
        self.requests_url = requests_url
        psutil.cpu_percent(interval=None)
        self._last_net = psutil.net_io_counters()
        self._last_t = time.monotonic()

    def _requests_per_min(self) -> Optional[float]:
        """Read requests_per_min from the local counter URL (JSON {"requests_per_min": n} or a plain number)."""
        if not self.requests_url:
            return None
        try:
            res = requests.get(self.requests_url, timeout=2)
            res.raise_for_status()
            try:
                data: Any = res.json()
            except ValueError:
                data = res.text.strip()
            value = data.get("requests_per_min") if isinstance(data, dict) else data
            return max(0.0, float(value)) if value is not None else None
        except (requests.RequestException, TypeError, ValueError):
            log.warning("could not read requests counter from %s", self.requests_url)
            return None

    def sample(self) -> Dict[str, Any]:
        """Return one metrics sample with a UTC timestamp."""
        now = time.monotonic()
        net = psutil.net_io_counters()
        elapsed = max(now - self._last_t, 0.001)
        in_kbps = max(0, net.bytes_recv - self._last_net.bytes_recv) * 8 / 1000 / elapsed
        out_kbps = max(0, net.bytes_sent - self._last_net.bytes_sent) * 8 / 1000 / elapsed
        self._last_net, self._last_t = net, now
        try:
            disk: Optional[float] = psutil.disk_usage("/").percent
        except OSError:
            disk = None
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "cpu_pct": round(psutil.cpu_percent(interval=None), 2),
            "mem_pct": round(psutil.virtual_memory().percent, 2),
            "net_in_kbps": round(in_kbps, 2),
            "net_out_kbps": round(out_kbps, 2),
            "disk_pct": disk,
            "requests_per_min": self._requests_per_min(),
        }


# ---------- sending ----------


class Sender:
    """Buffers samples for up to 10 minutes and sends them with exponential backoff."""

    def __init__(self, url: str, token: str, identity: Dict[str, Optional[str]]) -> None:
        """Set up the HTTP session and an empty buffer."""
        self.endpoint = url.rstrip("/") + "/api/ingest"
        self.identity = identity
        self.http = requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {token}", "User-Agent": f"optiserve-agent/{VERSION}"})
        self.buffer: Deque[Tuple[datetime, Dict[str, Any]]] = deque()
        self.backoff = 0.0
        self.next_try = 0.0

    def add(self, sample: Dict[str, Any]) -> None:
        """Queue a sample and drop anything older than the buffer window."""
        now = datetime.now(timezone.utc)
        self.buffer.append((now, sample))
        dropped = 0
        while self.buffer and now - self.buffer[0][0] > BUFFER_WINDOW:
            self.buffer.popleft()
            dropped += 1
        if dropped:
            log.warning("offline buffer full: dropped %d samples older than 10 minutes", dropped)

    def _fail(self, retry_after: Optional[float] = None) -> None:
        """Schedule the next attempt with exponential backoff (or the server's Retry-After)."""
        self.backoff = min(BACKOFF_MAX_S, self.backoff * 2 if self.backoff else BACKOFF_START_S)
        delay = max(self.backoff, retry_after or 0.0)
        self.next_try = time.monotonic() + delay
        log.warning("send failed; %d samples buffered; retrying in %.0f s", len(self.buffer), delay)

    def flush(self) -> None:
        """Send buffered samples in batches unless we are waiting out a backoff."""
        if time.monotonic() < self.next_try:
            return
        while self.buffer:
            batch: List[Dict[str, Any]] = [s for _, s in list(self.buffer)[:MAX_BATCH]]
            try:
                res = self.http.post(self.endpoint, json={"host": self.identity, "metrics": batch}, timeout=10)
            except requests.RequestException as exc:
                log.warning("cannot reach backend: %s", type(exc).__name__)
                self._fail()
                return
            if res.status_code == 200:
                for _ in batch:
                    self.buffer.popleft()
                if self.backoff:
                    log.info("backend reachable again")
                self.backoff, self.next_try = 0.0, 0.0
                continue
            if res.status_code == 401:
                log.error("backend rejected the agent token (invalid or revoked)")
                self._fail()
                return
            if res.status_code == 429:
                self._fail(float(res.headers.get("Retry-After", "60") or 60))
                return
            if 400 <= res.status_code < 500:
                # The backend will never accept this batch (e.g. a bad clock); drop it so newer data can flow.
                log.error("backend refused %d samples (HTTP %d): %s", len(batch), res.status_code, res.text[:300])
                for _ in batch:
                    self.buffer.popleft()
                continue
            self._fail()
            return


# ---------- main ----------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line flags, falling back to environment variables."""
    p = argparse.ArgumentParser(description="OptiServe metrics agent")
    p.add_argument("--url", default=os.environ.get("OPTISERVE_URL"), help="backend base URL (env OPTISERVE_URL)")
    p.add_argument("--token", default=os.environ.get("OPTISERVE_TOKEN"), help="agent token (env OPTISERVE_TOKEN)")
    p.add_argument(
        "--requests-url",
        default=os.environ.get("OPTISERVE_REQUESTS_URL"),
        help="optional local URL returning requests_per_min (env OPTISERVE_REQUESTS_URL)",
    )
    p.add_argument("--interval", type=float, default=float(os.environ.get("OPTISERVE_INTERVAL", "10")))
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args(argv)
    if not args.url or not args.token:
        p.error("--url and --token are required (or set OPTISERVE_URL and OPTISERVE_TOKEN)")
    return args


def main(argv: Optional[List[str]] = None) -> int:
    """Run the collect-and-send loop until stopped."""
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    running = {"on": True}

    def _stop(signum: int, _frame: Any) -> None:
        """Stop the loop on SIGTERM/SIGINT."""
        running["on"] = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    identity = detect_identity()
    log.info("optiserve-agent %s reporting as %s to %s", VERSION, identity["external_id"], args.url)
    collector = Collector(args.requests_url)
    sender = Sender(args.url, args.token, identity)
    next_tick = time.monotonic() + args.interval
    while running["on"]:
        time.sleep(max(0.0, next_tick - time.monotonic()))
        next_tick += args.interval
        if not running["on"]:
            break
        sender.add(collector.sample())
        sender.flush()
    log.info("stopped; %d unsent samples discarded", len(sender.buffer))
    return 0


if __name__ == "__main__":
    sys.exit(main())
