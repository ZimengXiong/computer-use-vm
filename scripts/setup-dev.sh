#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if ! command -v tart >/dev/null 2>&1; then
  echo "Installing Tart with Homebrew..."
  brew install cirruslabs/cli/tart
fi

rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -r requirements-vnc.txt

python3 -m compileall computer_use_vm guest/computer_use_vm_guest_agent.py
swiftc -O guest/ComputerUseVMGuestHelper.swift -o /tmp/computer-use-vm-guest-helper-check

echo "Setup complete."
./bin/computer-use-vm diagnose
