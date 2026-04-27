"""Configuration & paths for c2p."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _root() -> Path:
    here = Path(__file__).resolve().parent
    # walk up to find pyproject.toml
    for p in (here, *here.parents):
        if (p / "pyproject.toml").exists():
            return p
    return Path.cwd()


PROJECT_ROOT = _root()
DATA_DIR = Path(os.environ.get("C2P_DATA_DIR", PROJECT_ROOT / "data")).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class Settings:
    upstream_url: str = os.environ.get("C2P_UPSTREAM", "http://127.0.0.1:4141")
    gateway_host: str = os.environ.get("C2P_GATEWAY_HOST", "127.0.0.1")
    gateway_port: int = int(os.environ.get("C2P_GATEWAY_PORT", "8787"))
    upstream_port: int = int(os.environ.get("C2P_UPSTREAM_PORT", "4141"))
    upstream_rate_limit: int = int(os.environ.get("C2P_RATE_LIMIT", "10"))
    max_request_log: int = 32 * 1024
    max_response_log: int = 16 * 1024

    keys_db: Path = DATA_DIR / "keys.sqlite"
    usage_log: Path = DATA_DIR / "usage.log"
    pid_dir: Path = DATA_DIR / "pids"
    log_dir: Path = DATA_DIR / "logs"
    tunnel_url_file: Path = DATA_DIR / "tunnel_url.txt"


SETTINGS = Settings()
SETTINGS.pid_dir.mkdir(parents=True, exist_ok=True)
SETTINGS.log_dir.mkdir(parents=True, exist_ok=True)
