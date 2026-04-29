#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v tart >/dev/null 2>&1; then
  echo "Installing Tart with Homebrew..."
  brew install cirruslabs/cli/tart
fi

python3 -m venv .venv
.venv/bin/pip install -r requirements-vnc.txt

python3 -m compileall codex_vm_bridge guest/codex_vm_guest_agent.py
swiftc -O guest/CodexVMGuestHelper.swift -o /tmp/codex-vm-guest-helper-check

echo "Setup complete."
./bin/codex-vm-bridge diagnose
