"""c2p CLI."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import SETTINGS
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
