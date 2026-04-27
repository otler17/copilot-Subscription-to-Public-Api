#!/usr/bin/env bash
# Download cloudflared into ./bin/cloudflared if not on PATH.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HERE/bin/cloudflared"

if command -v cloudflared >/dev/null 2>&1; then
  echo "✓ cloudflared already on PATH ($(command -v cloudflared))"
  exit 0
fi
if [ -x "$DEST" ]; then
  echo "✓ cloudflared already at $DEST"
  exit 0
fi

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "unsupported arch: $ARCH"; exit 1 ;;
esac

URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-${OS}-${ARCH}"
echo "↓ downloading $URL"
mkdir -p "$HERE/bin"
curl -fsSL "$URL" -o "$DEST"
chmod +x "$DEST"
"$DEST" --version
