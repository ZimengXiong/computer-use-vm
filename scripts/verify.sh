#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m compileall computer_use_vm guest/computer_use_vm_guest_agent.py
swiftc -O guest/ComputerUseVMGuestHelper.swift -o /tmp/computer-use-vm-guest-helper-check
./bin/computer-use-vm diagnose >/tmp/computer-use-vm-diagnose.json

echo "Verification complete."
