"""Process supervision: starts/stops copilot-api, the gateway, and cloudflared.

Each process is started via subprocess.Popen with stdout/stderr to data/logs/.
PIDs live in data/pids/.  No systemd dependency.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import SETTINGS


@dataclass
class Service:
    name: str
    cmd: list[str]
    env: Optional[dict] = None
    cwd: Optional[Path] = None

    @property
    def pid_file(self) -> Path:
        return SETTINGS.pid_dir / f"{self.name}.pid"

    @property
    def log_file(self) -> Path:
        return SETTINGS.log_dir / f"{self.name}.log"

    def is_running(self) -> Optional[int]:
        if not self.pid_file.exists():
            return None
        try:
            pid = int(self.pid_file.read_text().strip())
        except ValueError:
            return None
        try:
            os.kill(pid, 0)
            return pid
        except ProcessLookupError:
            self.pid_file.unlink(missing_ok=True)
            return None
        except PermissionError:
            return pid

    def start(self) -> int:
        if pid := self.is_running():
            return pid
        env = {**os.environ, **(self.env or {})}
        log = self.log_file.open("a")
        log.write(f"\n=== starting {self.name} at {time.ctime()} ===\n")
        log.flush()
        proc = subprocess.Popen(
            self.cmd,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            env=env, cwd=self.cwd, start_new_session=True,
        )
        self.pid_file.write_text(str(proc.pid))
        return proc.pid

    def stop(self, timeout: float = 5.0) -> bool:
        pid = self.is_running()
        if not pid:
            return False
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self.is_running():
                self.pid_file.unlink(missing_ok=True)
                return True
            time.sleep(0.2)
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except Exception:
            pass
        self.pid_file.unlink(missing_ok=True)
        return True


def _resolve_cloudflared() -> str:
    candidate = shutil.which("cloudflared")
    if candidate:
        return candidate
    bundled = SETTINGS.pid_dir.parent / "bin" / "cloudflared"
    if bundled.exists():
        return str(bundled)
    raise RuntimeError(
        "cloudflared not found. Run: bash scripts/cloudflared-install.sh"
    )


def services() -> list[Service]:
    npx = shutil.which("npx") or shutil.which("bunx")
    if not npx:
        raise RuntimeError("Need `npx` or `bunx` on PATH to run copilot-api.")

    copilot = Service(
        name="copilot-api",
        cmd=[npx, "--yes", "copilot-api@latest", "start",
             "--port", str(SETTINGS.upstream_port),
             "--rate-limit", str(SETTINGS.upstream_rate_limit),
             "--wait"],
    )
    gateway = Service(
        name="gateway",
        cmd=[sys.executable, "-m", "uvicorn", "c2p.app:app",
             "--host", SETTINGS.gateway_host,
             "--port", str(SETTINGS.gateway_port),
             "--log-level", "warning"],
    )
    tunnel = Service(
        name="tunnel",
        cmd=[_resolve_cloudflared(), "tunnel",
             "--url", f"http://{SETTINGS.gateway_host}:{SETTINGS.gateway_port}",
             "--no-autoupdate"],
    )
    return [copilot, gateway, tunnel]


_TUNNEL_RE = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")


def detect_tunnel_url(timeout: float = 30.0) -> Optional[str]:
    """Tail the tunnel log until we find the *most recent* assigned hostname.

    Cloudflare quick tunnels get a fresh hostname on every restart, but the log
    is appended to, so we must always pick the last match — not the first.
    """
    log = SETTINGS.log_dir / "tunnel.log"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if log.exists():
            text = log.read_text(errors="replace")
            matches = _TUNNEL_RE.findall(text)
            if matches:
                url = matches[-1]
                SETTINGS.tunnel_url_file.write_text(url + "\n")
                return url
        time.sleep(0.5)
    return None


def cached_tunnel_url() -> Optional[str]:
    """Return the cached tunnel URL, but only if the tunnel service is alive.

    A leftover ``tunnel_url.txt`` from a previous run would otherwise mislead
    callers (e.g. ``c2p status``) into reporting a dead public URL after a
    crash or external kill of cloudflared.
    """
    if not SETTINGS.tunnel_url_file.exists():
        return None
    for s in services():
        if s.name == "tunnel":
            if not s.is_running():
                return None
            break
    return SETTINGS.tunnel_url_file.read_text().strip() or None


def start_all() -> dict:
    out = {}
    # quick tunnels mint a new hostname on every restart; truncate the log so
    # detect_tunnel_url() can't pick up a stale URL from a previous run.
    tunnel_log = SETTINGS.log_dir / "tunnel.log"
    try:
        tunnel_log.write_text("")
    except OSError:
        pass
    SETTINGS.tunnel_url_file.unlink(missing_ok=True)

    for s in services():
        out[s.name] = s.start()
        time.sleep(1.0)
    url = detect_tunnel_url()
    out["tunnel_url"] = url
    return out


def stop_all() -> dict:
    out = {}
    for s in reversed(services()):
        out[s.name] = s.stop()
    SETTINGS.tunnel_url_file.unlink(missing_ok=True)
    return out


def status_all() -> dict:
    return {s.name: s.is_running() for s in services()}
