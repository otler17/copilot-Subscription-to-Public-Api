# Stable hostnames with a named Cloudflare Tunnel

The default `cloudflared --url` mode creates an **ephemeral** hostname (e.g.
`https://something-random.trycloudflare.com`) that changes every restart.

For a stable URL like `https://copilot.example.com`, use a named tunnel.

## Prerequisites

- A domain on Cloudflare (free plan works).
- `cloudflared` installed (the project's installer handles this).

## Steps

```bash
# 1. log in (opens a browser, picks the zone)
./bin/cloudflared tunnel login

# 2. create a named tunnel — saves credentials JSON in ~/.cloudflared/
./bin/cloudflared tunnel create c2p

# 3. route a hostname on your zone to the tunnel
./bin/cloudflared tunnel route dns c2p copilot.example.com

# 4. write a tunnel config
mkdir -p ~/.cloudflared
cat > ~/.cloudflared/config.yml <<EOF
tunnel: c2p
credentials-file: $HOME/.cloudflared/<tunnel-uuid>.json
ingress:
  - hostname: copilot.example.com
    service: http://127.0.0.1:8787
  - service: http_status:404
EOF

# 5. replace the systemd ExecStart with:
#    ./bin/cloudflared tunnel run c2p
./bin/cloudflared tunnel run c2p
```

## Optional: Cloudflare Access policy

For a second authentication layer (e.g. require a Google login from a
specific email), add a Cloudflare Access self-hosted application on
`copilot.example.com`. The bearer-key check still applies inside the
gateway — Access just gates who can reach it.
