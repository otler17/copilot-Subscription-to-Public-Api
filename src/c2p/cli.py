"""c2p CLI."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import SETTINGS, PROJECT_ROOT
from . import keystore, runner


app = typer.Typer(help="Expose your local copilot-api as a public OpenAI-compatible API.",
                  no_args_is_help=True)
key_app = typer.Typer(help="Manage API keys")
app.add_typer(key_app, name="key")
console = Console()


@app.command()
def init():
    """Create data dirs and an empty key store."""
    SETTINGS.pid_dir.mkdir(parents=True, exist_ok=True)
    SETTINGS.log_dir.mkdir(parents=True, exist_ok=True)
    keystore.list_keys()  # touches sqlite
    console.print(f"[green]✓[/] Initialized at {SETTINGS.keys_db.parent}")


# ─────────────────────────── one-shot setup journey ──────────────────────────

_COPILOT_TOKEN_PATHS = [
    Path.home() / ".local/share/copilot-api/github_token",
    Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
    / "copilot-api/github_token",
]


def _step(n: int, total: int, title: str) -> None:
    console.print(f"\n[bold cyan]({n}/{total})[/] [bold]{title}[/]")


def _ok(msg: str) -> None:
    console.print(f"  [green]✓[/] {msg}")


def _warn(msg: str) -> None:
    console.print(f"  [yellow]![/] {msg}")


def _fail(msg: str) -> None:
    console.print(f"  [red]✗[/] {msg}")


def _have_node() -> Optional[str]:
    return shutil.which("npx") or shutil.which("bunx")


def _have_cloudflared() -> Optional[str]:
    found = shutil.which("cloudflared")
    if found:
        return found
    bundled = PROJECT_ROOT / "bin" / "cloudflared"
    return str(bundled) if bundled.exists() else None


def _is_authed() -> bool:
    return any(p.exists() and p.stat().st_size > 0 for p in _COPILOT_TOKEN_PATHS)


def _pick_or_create_key() -> keystore.ApiKey:
    keys = [k for k in keystore.list_keys() if not k.revoked]
    if keys:
        console.print(f"  [dim]found {len(keys)} existing key(s):[/]")
        for k in keys:
            console.print(f"    • [bold]{k.name}[/] [dim]{k.secret}[/]")
        if not typer.confirm("  create another key?", default=False):
            return keys[0]

    default_name = "friend" if not keystore.get_by_name("friend") else f"key-{int(time.time())}"
    name = typer.prompt("  key name (label)", default=default_name).strip()
    while keystore.get_by_name(name):
        _warn(f"name '{name}' already taken")
        name = typer.prompt("  key name (label)").strip()
    rpm = typer.prompt("  max requests per minute (0 = unlimited)",
                       default=30, type=int)
    return keystore.add_key(name, max_rpm=rpm)


def _summary_panel(url: Optional[str], key: keystore.ApiKey) -> None:
    base_oai = f"{url}/v1" if url else "http://127.0.0.1:8787/v1"
    base_ant = url or "http://127.0.0.1:8787"
    secret = key.secret

    body_lines = [
        f"[bold]API key (name: {key.name}):[/]",
        f"  [cyan]{secret}[/]",
        "",
        f"[bold]OpenAI base URL:[/]    [cyan]{base_oai}[/]",
        f"[bold]Anthropic base URL:[/] [cyan]{base_ant}[/]",
        "",
        "[bold]Python — OpenAI SDK[/]",
        f"  [dim]from openai import OpenAI[/]",
        f"  [dim]c = OpenAI(base_url=\"{base_oai}\", api_key=\"{secret}\")[/]",
        "",
        "[bold]Python — Anthropic SDK[/]",
        f"  [dim]from anthropic import Anthropic[/]",
        f"  [dim]c = Anthropic(base_url=\"{base_ant}\", api_key=\"{secret}\")[/]",
        "",
        "[bold]Claude Code CLI[/]",
        f"  [dim]export ANTHROPIC_BASE_URL=\"{base_ant}\"[/]",
        f"  [dim]export ANTHROPIC_AUTH_TOKEN=\"{secret}\"[/]",
        f"  [dim]claude[/]",
    ]
    if url:
        body_lines += ["",
                       f"[bold]Tracker:[/] [cyan]{url}/usage-summary?key={secret}[/]"]
    console.print(Panel("\n".join(body_lines),
                        title="🎉 c2p is up", border_style="green"))


@app.command()
def setup(
    yes: bool = typer.Option(False, "--yes", "-y",
                             help="non-interactive: accept all defaults"),
    skip_start: bool = typer.Option(False, "--skip-start",
                                    help="don't start services at the end"),
):
    """One-command interactive setup: deps → auth → key → start → summary."""
    total = 5
    console.print(Panel.fit(
        "[bold]Welcome to c2p[/]\n"
        "Expose your local copilot-api as a public OpenAI- and Anthropic-\n"
        "compatible API. This wizard will get you running in a few steps.",
        border_style="cyan",
    ))

    # 1. prerequisites
    _step(1, total, "Checking prerequisites")
    node = _have_node()
    if not node:
        _fail("Node.js not found. Install it (≥ 18) from https://nodejs.org "
              "or your distro, then re-run `c2p setup`.")
        raise typer.Exit(1)
    _ok(f"node available ({node})")

    cf = _have_cloudflared()
    if not cf:
        _warn("cloudflared not found — installing into ./bin/")
        rc = subprocess.call(["bash", str(PROJECT_ROOT / "scripts" / "cloudflared-install.sh")])
        if rc != 0:
            _fail("cloudflared install failed; see scripts/cloudflared-install.sh")
            raise typer.Exit(rc)
        cf = _have_cloudflared()
    _ok(f"cloudflared available ({cf})")

    # 2. GitHub Copilot auth
    _step(2, total, "GitHub Copilot login")
    if _is_authed():
        _ok("already logged in (token cached at ~/.local/share/copilot-api/)")
    else:
        _warn("not logged in — starting GitHub device-flow login")
        console.print("  [dim]a code will appear; paste it in the URL shown.[/]")
        rc = subprocess.call(["npx", "--yes", "copilot-api@latest", "auth"])
        if rc != 0 or not _is_authed():
            _fail("auth did not complete")
            raise typer.Exit(rc or 1)
        _ok("logged in")

    # 3. API key
    _step(3, total, "API key")
    if yes and not keystore.list_keys(include_revoked=False):
        key = keystore.add_key("friend", max_rpm=30)
        _ok(f"created key '{key.name}'")
    elif yes:
        key = [k for k in keystore.list_keys() if not k.revoked][0]
        _ok(f"using existing key '{key.name}'")
    else:
        key = _pick_or_create_key()
        _ok(f"using key '{key.name}'")

    if skip_start:
        console.print("\n[dim]--skip-start set; not starting services.[/]")
        _summary_panel(None, key)
        return

    # 4. start services
    _step(4, total, "Starting services (copilot-api, gateway, cloudflared)")
    with console.status("  bringing services up..."):
        out = runner.start_all()
    for name, pid in out.items():
        if name == "tunnel_url":
            continue
        if pid:
            _ok(f"{name} pid {pid}")
        else:
            _warn(f"{name} did not start — check {SETTINGS.log_dir / (name + '.log')}")

    # 5. tunnel URL + summary
    _step(5, total, "Detecting public tunnel URL")
    url = out.get("tunnel_url") or runner.detect_tunnel_url(timeout=20.0)
    if url:
        _ok(url)
    else:
        _warn("tunnel URL not detected yet — run `c2p status` in a few seconds")

    _summary_panel(url, key)


# ─────────────────────────────────────────────────────────────────────────────


@app.command()
def auth():
    """Run the GitHub Copilot device-flow login (delegates to copilot-api)."""
    cmd = ["npx", "--yes", "copilot-api@latest", "auth"]
    console.print(f"[dim]$ {' '.join(cmd)}[/]")
    sys.exit(subprocess.call(cmd))


@app.command()
def start():
    """Start copilot-api, the auth gateway, and the cloudflared tunnel."""
    if not keystore.list_keys(include_revoked=False):
        console.print("[yellow]⚠  No API keys yet. Create one with: c2p key add --name friend[/]")
    out = runner.start_all()
    console.print(json.dumps({k: v for k, v in out.items() if k != "tunnel_url"}, indent=2))
    if out.get("tunnel_url"):
        url = out["tunnel_url"]
        console.print(f"\n[bold green]OpenAI base URL:[/]    {url}/v1")
        console.print(f"[bold green]Anthropic base URL:[/] {url}")
    else:
        console.print("[yellow]Tunnel URL not detected yet — run `c2p status` in a few seconds.[/]")


@app.command()
def stop():
    """Stop all services."""
    out = runner.stop_all()
    console.print(json.dumps(out, indent=2))


@app.command()
def status():
    """Show service status, tunnel URL, and keys."""
    svc = runner.status_all()
    url = runner.cached_tunnel_url() or runner.detect_tunnel_url(timeout=2.0)

    t = Table(title="services")
    t.add_column("name"); t.add_column("pid"); t.add_column("log")
    for name, pid in svc.items():
        t.add_row(name, str(pid) if pid else "[red]down[/]",
                  str(SETTINGS.log_dir / f"{name}.log"))
    console.print(t)

    if url:
        console.print(f"\n[bold]OpenAI base URL:[/]    [cyan]{url}/v1[/]")
        console.print(f"[bold]Anthropic base URL:[/] [cyan]{url}[/]   [dim](for Anthropic SDK / Claude Code)[/]")
        console.print(f"[bold]Tracker:[/]            [cyan]{url}/usage-summary?key=<your-key>[/]")
    else:
        console.print("\n[yellow]No tunnel URL recorded yet.[/]")

    keys = keystore.list_keys()
    if keys:
        kt = Table(title="API keys")
        kt.add_column("name"); kt.add_column("secret"); kt.add_column("rpm")
        kt.add_column("models"); kt.add_column("revoked"); kt.add_column("last used")
        for k in keys:
            kt.add_row(
                k.name, k.secret, str(k.max_rpm or "∞"),
                ",".join(k.models) or "all",
                "yes" if k.revoked else "no",
                time.strftime("%Y-%m-%d %H:%M", time.localtime(k.last_used_at))
                if k.last_used_at else "—",
            )
        console.print(kt)


@app.command()
def logs(tail: int = typer.Option(50, "--tail", "-n"),
         follow: bool = typer.Option(False, "--follow", "-f")):
    """Show the request/response log."""
    p: Path = SETTINGS.usage_log
    if not p.exists():
        console.print("[dim]no log yet[/]")
        return
    cmd = ["tail", f"-n{tail}"]
    if follow:
        cmd.append("-f")
    cmd.append(str(p))
    subprocess.call(cmd)


@app.command()
def models():
    """List models exposed by the upstream copilot-api."""
    import httpx
    try:
        r = httpx.get(f"{SETTINGS.upstream_url}/v1/models", timeout=5.0)
        r.raise_for_status()
        for m in r.json().get("data", []):
            console.print(f"- {m.get('id')}  [dim]({m.get('owned_by','?')})[/]")
    except Exception as e:
        console.print(f"[red]error:[/] {e}")
        raise typer.Exit(1)


# ---------- key subcommands ----------

@key_app.command("add")
def key_add(
    name: str = typer.Option(..., "--name", help="label, e.g. 'friend' or 'app-mobile'"),
    max_rpm: int = typer.Option(0, "--max-rpm",
                                help="requests per minute, 0 = unlimited"),
    allow_models: str = typer.Option("", "--allow-models",
                                     help="comma-separated model allow-list; empty = all"),
):
    """Create a new API key."""
    models_ = [m.strip() for m in allow_models.split(",") if m.strip()]
    try:
        k = keystore.add_key(name, max_rpm=max_rpm, allow_models=models_)
    except Exception as e:
        console.print(f"[red]error:[/] {e}")
        raise typer.Exit(1)
    console.print(f"[green]✓[/] created key [bold]{k.name}[/]:\n  [cyan]{k.secret}[/]")


@key_app.command("list")
def key_list():
    keys = keystore.list_keys()
    if not keys:
        console.print("[dim]no keys[/]")
        return
    t = Table()
    t.add_column("name"); t.add_column("secret"); t.add_column("rpm")
    t.add_column("revoked"); t.add_column("last used")
    for k in keys:
        t.add_row(
            k.name, k.secret, str(k.max_rpm or "∞"),
            "yes" if k.revoked else "no",
            time.strftime("%Y-%m-%d %H:%M", time.localtime(k.last_used_at))
            if k.last_used_at else "—",
        )
    console.print(t)


@key_app.command("revoke")
def key_revoke(name_or_secret: str):
    if keystore.revoke(name_or_secret):
        console.print(f"[green]✓[/] revoked {name_or_secret}")
    else:
        console.print(f"[red]not found:[/] {name_or_secret}")
        raise typer.Exit(1)


@key_app.command("show")
def key_show(name: str):
    k = keystore.get_by_name(name)
    if not k:
        console.print(f"[red]no key named[/] {name}")
        raise typer.Exit(1)
    console.print_json(json.dumps({
        "name": k.name, "secret": k.secret, "max_rpm": k.max_rpm,
        "models": k.models, "revoked": k.revoked,
        "created_at": k.created_at, "last_used_at": k.last_used_at,
    }))


if __name__ == "__main__":
    app()
