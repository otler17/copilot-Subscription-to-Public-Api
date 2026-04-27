# Architecture

```
client (any OpenAI SDK)
    │  HTTPS
    ▼
Cloudflare Tunnel (cloudflared)
    │  HTTP to 127.0.0.1:8787
    ▼
c2p gateway (FastAPI)   ── auth, rate limit, logging
    │  HTTP to 127.0.0.1:4141
    ▼
copilot-api (Hono / Bun, by ericc-ch)
    │  HTTPS
    ▼
GitHub Copilot API (your OAuth token)
```

## Components

- **copilot-api** (`ericc-ch/copilot-api`, run via `npx`) — converts the
  Copilot internal API into OpenAI/Anthropic-compatible endpoints. Bound to
  `127.0.0.1:4141`.
- **c2p gateway** (`src/c2p/app.py`) — thin FastAPI reverse proxy that:
  - validates `Authorization: Bearer sk-...` against the SQLite key store;
  - enforces per-key model allow-list and RPM limits;
  - logs the request body, response body, status, and duration to
    `data/usage.log` (JSONL).
- **cloudflared** — runs a quick or named tunnel that exposes the gateway
  via HTTPS to the public internet.
- **CLI** (`src/c2p/cli.py`) — Typer app that supervises all three processes
  and manages keys.

## Data layout

```
data/
├── keys.sqlite      # API keys
├── usage.log        # JSONL of every proxied request and response
├── tunnel_url.txt   # cached current tunnel URL
├── pids/            # one PID file per supervised process
└── logs/            # stdout/stderr of each process
```

## Why FastAPI + httpx and not LiteLLM?

LiteLLM Proxy is the natural choice for multi-key OpenAI-compatible
gateways, but its virtual-key feature requires a Postgres+Prisma stack.
For a single-host, single-friend setup, a 200-line FastAPI app is simpler,
has no daemon dependencies, and lets us log full request/response bodies
without writing custom callbacks.
