# copilot-Subscription-to-Public-Api

Turn a locally-running [`copilot-api`](https://github.com/ericc-ch/copilot-api)
instance into a **public, OpenAI-compatible API** that you can share with anyone
using a regular `sk-...` API key.

```
client app  ──HTTPS──►  Cloudflare Tunnel  ──►  c2p auth gateway  ──►  copilot-api  ──►  GitHub Copilot
                                                  (sk- keys, logs)       (localhost)
```

## ✨ Features

- **OpenAI- & Anthropic-compatible** — drop-in for the OpenAI SDK
  (Continue, Aider, Open WebUI, …) **and** for the Anthropic SDK / Claude Code
  via `/v1/messages`.
- **API key auth** — issue, list, and revoke `sk-...` keys with a single CLI.
- **Per-key tracking** — every request logged with model, prompt, response,
  status, latency, IP.
- **Browser-friendly viewer** — open the live log in a single HTML page.
- **One public URL** via Cloudflare Tunnel (free, no domain required for the
  quick-tunnel mode).
- **systemd-friendly** — user units provided so everything auto-restarts after
  reboot.
- **Single command setup** (`make install && make up`).

> ⚠️ **TOS warning:** GitHub Copilot is licensed to *you*. Re-exposing it via
> proxy violates GitHub's Copilot terms and abuse-detection systems can
> suspend your account. Use rate limits, share with one trusted person, and
> read [`docs/TOS.md`](docs/TOS.md) before publishing.

---

## 📦 Requirements

| Tool | Version | Why |
|---|---|---|
| Python | ≥ 3.10 | runs the auth gateway |
| Node.js | ≥ 18 (or [Bun](https://bun.sh)) | runs `copilot-api` via `npx` |
| `cloudflared` | latest | public HTTPS tunnel |
| GitHub account with a Copilot subscription | — | the upstream provider |

The installer (`scripts/install.sh`) installs the Python deps and downloads
`cloudflared` automatically. It does **not** install Node — install that from
your distro or [nodejs.org](https://nodejs.org) first.

### About `copilot-api`

This project is a **wrapper** around [`ericc-ch/copilot-api`](https://github.com/ericc-ch/copilot-api)
— the reverse-engineered Copilot proxy that does the actual GitHub Copilot
talking. **You do NOT need to clone or install it separately.** `c2p` runs it
via `npx --yes copilot-api@latest start ...` on demand, so all you need is
Node.js on your `PATH`.

You only need to do this once:

```bash
c2p auth        # delegates to: npx copilot-api auth
```

…which performs the GitHub device-flow login and caches the token in
`~/.local/share/copilot-api/` (used by every subsequent run). After that,
`c2p start` will keep the upstream `copilot-api` process running for you.

> If you'd rather pin a specific version or run `copilot-api` from source,
> start it yourself on `127.0.0.1:4141` and set `C2P_UPSTREAM_PORT` /
> `C2P_UPSTREAM` accordingly — the gateway will route to whatever is
> listening there.

All credit for the upstream Copilot proxy belongs to
[**@ericc-ch**](https://github.com/ericc-ch). This project simply adds API
key auth, quotas, logging, and a public tunnel on top.

---

## 🚀 Quick start

```bash
git clone https://github.com/otler17/copilot-Subscription-to-Public-Api.git
cd copilot-Subscription-to-Public-Api

make            # one-command interactive setup
```

That's it. `make` (alias for `make setup`) runs `c2p setup`, which:

1. checks Node.js + downloads `cloudflared` if missing,
2. runs the GitHub Copilot device-flow login (skipped if already logged in),
3. creates your first API key (skipped/extended if keys already exist),
4. starts `copilot-api` + the auth gateway + the Cloudflare tunnel,
5. prints a copy-pasteable summary with both the OpenAI and Anthropic base
   URLs and ready-to-use SDK / Claude Code snippets.

Re-run `make` anytime — every step is idempotent. For non-interactive use:

```bash
./bin/c2p setup --yes        # accept all defaults
./bin/c2p setup --skip-start # configure only, don't launch services
```

When you want to inspect or manage things later:

```bash
./bin/c2p status             # public URL, keys, PIDs, model list
./bin/c2p key add --name app-mobile --max-rpm 60
./bin/c2p stop
```

---

## 🔧 What gets started

| Service | Port | Process |
|---|---|---|
| copilot-api | `127.0.0.1:4141` | `npx copilot-api start` |
| c2p auth gateway | `127.0.0.1:8787` | `uvicorn c2p.app:app` |
| Cloudflare Tunnel | → 8787 | `cloudflared tunnel --url ...` |

Only `cloudflared` is exposed publicly. The other two bind to `127.0.0.1`
so nothing leaks out without the API key.

All state (keys, logs, tunnel URL, PID files) lives under `./data/` by
default. Override with the `C2P_DATA_DIR` env var.

---

## 🗂 CLI overview

```
c2p setup           # ⭐ one-command interactive onboarding (deps, auth, key, start)
c2p init            # create data/, write defaults
c2p auth            # device-flow login to GitHub Copilot (delegates to copilot-api)
c2p start           # start all 3 services in the background
c2p stop            # stop them
c2p status          # public URL, keys, PIDs, model list
c2p logs [--tail N] # stream the request log
c2p doctor          # end-to-end health check (upstream + gateway + tunnel + round-trip)

c2p key add --name <label> [--max-rpm N] [--allow-models a,b]
c2p key list
c2p key revoke <key-or-name>
c2p key show <name>

c2p models          # list models exposed by the upstream copilot-api
```

---

## 🔑 Using the key from a client

The gateway speaks **two protocols** on the same tunnel — pick whichever your
client supports:

| Style | Base URL | Header |
|---|---|---|
| OpenAI-compatible | `https://<tunnel>.trycloudflare.com/v1` | `Authorization: Bearer sk-...` |
| Anthropic-compatible | `https://<tunnel>.trycloudflare.com` | `x-api-key: sk-...` |

### OpenAI SDK (Python)

```python
from openai import OpenAI

c = OpenAI(
    base_url="https://<your-tunnel>.trycloudflare.com/v1",
    api_key="sk-friend-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
)
resp = c.chat.completions.create(
    model="gpt-4.1",
    messages=[{"role": "user", "content": "hello!"}],
)
print(resp.choices[0].message.content)
```

### Anthropic SDK (Python)

```python
from anthropic import Anthropic

c = Anthropic(
    base_url="https://<your-tunnel>.trycloudflare.com",
    api_key="sk-friend-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
)
msg = c.messages.create(
    model="claude-sonnet-4",
    max_tokens=1024,
    messages=[{"role": "user", "content": "hello!"}],
)
print(msg.content[0].text)
```

### Claude Code CLI

```bash
export ANTHROPIC_BASE_URL="https://<your-tunnel>.trycloudflare.com"
export ANTHROPIC_AUTH_TOKEN="sk-friend-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
claude
```

Both styles authenticate with the **same** `sk-...` key — the gateway accepts
`Authorization: Bearer`, `x-api-key`, or `?key=` query param interchangeably,
and the Anthropic `/v1/messages` requests are forwarded straight to
`copilot-api`'s native Anthropic endpoint.

---

## 📊 Tracking & viewer

Every request appends a JSON line to `data/usage.log`:

```json
{"event":"request","ts":...,"key":"friend","model":"gpt-4.1","ip":"...",
 "request_body":{...},"summary":{"model":"gpt-4.1","message_count":3}}
{"event":"response","ts":...,"key":"friend","status":200,"duration_ms":812,
 "response_body":{...}}
```

Two ways to read it:

- **JSON endpoint:** `GET /usage-summary?key=<your-key>` (Bearer also works)
- **Browser viewer:** open `viewer/index.html` (single static page, points to
  your tunnel URL — paste the master/friend key in the form).

---

## 🐳 Docker (alternative to local install)

```bash
docker compose up -d
```

This runs the auth gateway + cloudflared in containers; `copilot-api` still
runs on the host (it needs your Copilot device login).

---

## 🔄 Auto-start on boot (systemd --user)

```bash
make systemd
systemctl --user enable --now c2p.target
loginctl enable-linger $USER     # so it survives logout
```

This installs three units: `c2p-copilot-api.service`, `c2p-gateway.service`,
`c2p-tunnel.service`, all bundled under `c2p.target`.

---

## ❓ Troubleshooting

**Tip:** run `./bin/c2p doctor` — it tests every layer (copilot-api → gateway
→ tunnel → end-to-end round-trip via the public URL) and tells you exactly
where it breaks.

- **Claude Code says `ConnectionRefused` / `FailedToOpenSocket`** — almost
  always a stale tunnel URL. Cloudflare quick-tunnels mint a new hostname on
  every restart. Always re-share the URL from `./bin/c2p status` (or
  `c2p doctor`) after a restart, not the one you copied last time.
- **`copilot-api` won't start** — run `npx copilot-api auth` once to log in.
- **Tunnel URL changed after reboot** — quick tunnels are ephemeral. For a
  stable URL, set `TUNNEL_HOSTNAME=copilot.yourdomain.com` and follow
  [`docs/named-tunnel.md`](docs/named-tunnel.md).
- **401 invalid api key** — check `c2p key list`, regenerate with
  `c2p key add`.
- **Friend hits rate limit** — bump `--max-rpm` or remove `--rate-limit` from
  the upstream config in `data/config.toml`.

---

## 📁 Layout

```
copilot-Subscription-to-Public-Api/
├── README.md
├── LICENSE
├── Makefile
├── pyproject.toml
├── requirements.txt
├── bin/c2p                    # CLI entrypoint (calls src/c2p/cli.py)
├── src/c2p/
│   ├── app.py                 # FastAPI auth gateway
│   ├── cli.py                 # CLI commands
│   ├── config.py              # paths + settings
│   ├── keystore.py            # key add/list/revoke (sqlite)
│   └── runner.py              # process supervision (start/stop/status)
├── viewer/index.html          # live log viewer (static)
├── systemd/                   # user service units
├── scripts/
│   ├── install.sh             # one-shot installer
│   └── cloudflared-install.sh # downloads cloudflared binary
├── docker-compose.yml
├── Dockerfile.gateway
├── docs/
│   ├── TOS.md
│   ├── named-tunnel.md
│   └── architecture.md
└── tests/
```

---

## 📜 License

[MIT](LICENSE) — do whatever, don't blame us if Copilot bans you.
