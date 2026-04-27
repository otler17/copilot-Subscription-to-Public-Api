#!/usr/bin/env bash
# Install systemd --user units so c2p autorestarts on boot.
set -e
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$DEST"
for f in c2p-copilot-api.service c2p-gateway.service c2p-tunnel.service c2p.target; do
  sed "s|@PROJECT@|$HERE|g" "$HERE/systemd/$f" > "$DEST/$f"
done
systemctl --user daemon-reload
echo "✓ installed units to $DEST"
echo "  systemctl --user enable --now c2p.target"
echo "  loginctl enable-linger \$USER   # to keep running after logout"
