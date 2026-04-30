# Computer Use VM

Let agents run disposable VMs.

This is a small bridge for running macOS GUI and terminal work inside Tart or UTM VMs instead of letting an agent drive your host desktop. The normal flow is: clone a prepared local base VM, mount the current repo into it, run commands there, use the guest agent for screenshots/accessibility/clicks, then delete the clone.

It does not ship a macOS base image. Each machine builds its own base locally. That keeps Apple software, privacy grants, user state, caches, and machine-specific data out of GitHub, npm, releases, and Hugging Face.

## Install

Install the Codex skill from npm:

```bash
npx computer-use-vm install-skill
```

From a checkout, use:

```bash
npm run install-skill
```

You also need Tart on the host:

```bash
brew install cirruslabs/cli/tart
```

VNC fallback is optional:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-vnc.txt
```

## Build A Base

Build the base once per machine:

```bash
codex-vm-bridge diagnose
codex-vm-bridge prepare-base codex-tahoe-base
codex-vm-bridge clone --backend tart codex-tahoe-base codex-vm-computer-base
codex-vm-bridge start --backend tart codex-vm-computer-base --vnc
codex-vm-bridge install-agent --backend tart codex-vm-computer-base
codex-vm-bridge provision-dev-tools --backend tart codex-vm-computer-base
codex-vm-bridge stop --backend tart codex-vm-computer-base
```

During that first VNC run, macOS may ask for Screen Recording and Accessibility permissions inside the guest. Approve those for the guest agent/helper. Normal userland code cannot silently grant them.

`provision-dev-tools` installs Homebrew if needed, then XcodeGen, Make, xcbeautify, and swiftformat. Full `xcodebuild` and SwiftLint need full `/Applications/Xcode.app`; Command Line Tools alone are not enough.

## Use It

For a task, clone the base and mount your current repo:

```bash
codex-vm-bridge clone --backend tart codex-vm-computer-base task-vm
codex-vm-bridge start --backend tart task-vm --vnc --mount "repo:$PWD:tag=repo"
codex-vm-bridge ip --backend tart task-vm
```

The mounted repo shows up in the guest at `/Volumes/My Shared Files/repo`, so agents can run real terminal commands without copying the project:

```bash
codex-vm-bridge exec --backend tart task-vm zsh -lc 'cd /Volumes/My\ Shared\ Files/repo && xcodegen generate'
```

If a mount is not available, copy a file or folder:

```bash
codex-vm-bridge push --backend tart task-vm ./MyProject /Users/admin/MyProject
```

For GUI work, use the guest agent:

```bash
codex-vm-bridge agent screenshot --host <guest-ip> --output /tmp/vm.png
codex-vm-bridge agent ax-tree --host <guest-ip>
codex-vm-bridge agent ax-press --host <guest-ip> --id <element-id>
codex-vm-bridge agent type --host <guest-ip> --text "hello"
```

Prefer accessibility actions when you can; use coordinate clicks and VNC as recovery tools.

## MCP

Run:

```bash
codex-vm-bridge mcp
```

The MCP server exposes VM lifecycle, `vm_exec`, `vm_push`, and the guest-agent screenshot/accessibility/input tools. See [examples/mcp.json](examples/mcp.json).

## Notes

`codex-vm-computer-base` is just a local Tart VM name. Do not upload or redistribute it. If another machine needs the bridge, install the package there and build a fresh local base.

UTM support exists for local VMs, but Tart is the main path for disposable macOS VM workflows.
