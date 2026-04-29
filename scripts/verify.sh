#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python3 -m compileall codex_vm_bridge guest/codex_vm_guest_agent.py
swiftc -O guest/CodexVMGuestHelper.swift -o /tmp/codex-vm-guest-helper-check
./bin/codex-vm-bridge diagnose >/tmp/codex-vm-bridge-diagnose.json

if [ -d "skills/codex-vm-computer" ] && [ -f "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" ]; then
  python3 "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" skills/codex-vm-computer
fi

echo "Verification complete."
