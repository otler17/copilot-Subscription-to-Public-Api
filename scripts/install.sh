#!/usr/bin/env bash
# One-shot installer: creates venv, installs python deps, downloads cloudflared.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

PY=${PY:-python3}
if [ ! -d .venv ]; then
  echo "→ creating venv"
  $PY -m venv .venv
fi
.venv/bin/pip install --upgrade --quiet pip wheel
.venv/bin/pip install --quiet -e .

bash scripts/cloudflared-install.sh

if ! command -v npx >/dev/null 2>&1 && ! command -v bunx >/dev/null 2>&1; then
  echo "⚠  No npx or bunx found. Install Node.js (>=18) or Bun before running 'c2p start'."
fi

echo
echo "✅ installed.  Next steps:"
echo "   .venv/bin/c2p auth                       # GitHub Copilot login"
echo "   .venv/bin/c2p key add --name friend      # issue an API key"
echo "   .venv/bin/c2p start                      # launch the public API"
echo "   .venv/bin/c2p status                     # show URL + keys"
