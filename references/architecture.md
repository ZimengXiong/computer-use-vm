# Computer Use VM Architecture

The bridge has three parts:

1. Host CLI/MCP server in `computer_use_vm`.
2. VM backend adapters for Tart and UTM.
3. Guest agent in `guest/`, composed of a Python HTTP server and Swift native helper.

The preferred control path is:

```text
Agent -> MCP stdio -> host bridge -> guest HTTP agent -> native macOS APIs
```

This avoids driving the host desktop or a VM viewer window. It supports hidden/headless VM runs while preserving screen introspection through guest-native screenshots.

Tart is the primary backend for performance and unattended work. UTM is supported for existing local VMs and for `--hide`/`--disposable` runs, but `utmctl` requires macOS Automation permission from a logged-in GUI session.

Local prepared base: `computer-use-vm-base`.

This base was created from `computer-use-pppc-test` after macOS privacy prompts were approved inside the VM. It includes `/Users/admin/computer-use-vm-agent`, a compiled Swift helper, and the LaunchAgent `/Users/admin/Library/LaunchAgents/local.computer-use.vm-agent.plist`, which starts the HTTP agent on port 7042 in the logged-in GUI session. A verification clone successfully returned a native screenshot through direct HTTP at `/tmp/computer-use-base-verify-native.png`.

The current helper also exposes `ax-tree`, which returns the focused guest app/window accessibility tree with roles, titles, values, enabled/focused state, frames, and actions. It supports semantic actions by traversal id: `ax-press`, `ax-click`, and `ax-set-value`. This is the main semantic bridge needed to approach native Computer Use behavior.
