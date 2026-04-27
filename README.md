# copilot-Api-to-Public-Api

Turn a locally-running [`copilot-api`](https://github.com/ericc-ch/copilot-api)
instance into a **public, OpenAI-compatible API** that you can share with anyone
using a regular `sk-...` API key.

```
client app  ──HTTPS──►  Cloudflare Tunnel  ──►  c2p auth gateway  ──►  copilot-api  ──►  GitHub Copilot
                                                  (sk- keys, logs)       (localhost)
```

## ✨ Features

- **OpenAI-compatible** — drop-in replacement for the OpenAI Python/JS SDK,
  Continue, Aider, Open WebUI, etc.
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

---

## 🚀 Quick start

```bash
git clone https://github.com/<you>/copilot-Api-to-Public-Api.git
cd copilot-Api-to-Public-Api

# 1. install Python deps + cloudflared
make install

# 2. one-time GitHub Copilot device-flow login (opens a URL, paste the code)
make auth

# 3. issue a key for your friend
./bin/c2p key add --name friend --max-rpm 30

# 4. start everything (copilot-api + auth gateway + cloudflared)
make up

# 5. read the public URL + the friend's key
./bin/c2p status
```

The output of `c2p status` is what you send to your friend. Done.

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
c2p init            # create data/, write defaults
c2p auth            # device-flow login to GitHub Copilot (delegates to copilot-api)
c2p start           # start all 3 services in the background
c2p stop            # stop them
c2p status          # public URL, keys, PIDs, model list
c2p logs [--tail N] # stream the request log

c2p key add --name <label> [--max-rpm N] [--allow-models a,b]
c2p key list
c2p key revoke <key-or-name>
c2p key show <name>

c2p models          # list models exposed by the upstream copilot-api
```

---

## 🔑 Using the key from a client

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

Anthropic-style endpoints (`/v1/messages`) are also forwarded if `copilot-api`
is configured for them.

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
copilot-Api-to-Public-Api/
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
