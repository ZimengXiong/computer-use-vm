#!/usr/bin/env bash
set -euo pipefail

BRIDGE="${BRIDGE:-./bin/codex-vm-bridge}"
BASE="${BASE:-codex-vm-computer-base}"
TASK="${TASK:-codex-vm-task-$(date +%s)}"

"$BRIDGE" clone --backend tart "$BASE" "$TASK"
"$BRIDGE" start --backend tart "$TASK" --vnc

IP=""
for _ in {1..60}; do
  IP="$("$BRIDGE" ip --backend tart "$TASK" | python3 -c 'import json,sys; print((json.load(sys.stdin) or [""])[0])')"
  if [ -n "$IP" ] && "$BRIDGE" agent ping --host "$IP" >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

if [ -z "$IP" ]; then
  echo "VM did not become ready" >&2
  exit 1
fi

"$BRIDGE" agent screenshot --host "$IP" --output /tmp/codex-vm-task.png
"$BRIDGE" agent ax-tree --host "$IP" --depth 5 --max-children 80

echo "Task VM: $TASK"
echo "Guest IP: $IP"
