#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$UNIT_DIR"
install -m 0644 "$ROOT/systemd/chef-claw.service" "$UNIT_DIR/chef-claw.service"
systemctl --user daemon-reload
systemctl --user enable --now chef-claw.service
systemctl --user --no-pager --full status chef-claw.service
