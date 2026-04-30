# Codex VM Bridge

Codex VM Bridge runs macOS GUI work inside disposable Tart or UTM virtual machines instead of controlling the host desktop directly.

It provides:

- VM lifecycle commands for Tart and UTM
- a guest macOS HTTP agent
- native guest screenshots
- guest Accessibility tree introspection
- semantic AX actions by element id
- coordinate click/type/key fallback
- in-guest terminal command execution
- Tart directory mounts for direct host workspace access
- file/folder copy fallback
- VNC fallback for bootstrap and visual recovery
- a Codex skill bundle
- a minimal MCP stdio server

The goal is to get close to native Codex Computer Use behavior while preserving VM isolation and repeatability.

## Architecture

```text
Codex
  -> codex-vm-bridge CLI/MCP server
      -> Tart or UTM VM backend
      -> guest HTTP agent
          -> Swift helper
              -> screencapture, CGEvent, AXUIElement, NSPasteboard
```

The fastest path is the in-guest agent. VNC is only a fallback for first-run permission approval and visual recovery.

## Requirements

- Apple Silicon Mac
- macOS host with Homebrew
- Tart for the recommended backend
- Xcode Command Line Tools in the guest for compiling the helper
- Screen Recording and Accessibility grants inside the prepared VM

Install Tart:

```bash
brew install cirruslabs/cli/tart
```

Optional VNC fallback dependency:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-vnc.txt
```

## Install The Skill

From this repository checkout:

```bash
npm install
npm run install-skill
```

After publishing to npm, users can install the Codex skill with:

```bash
npx codex-vm-bridge install-skill
```

The npm package installs only the bridge source and skill files. It does not include or download a prepared macOS VM image.

## Quick Start

From the repository root:

```bash
./bin/codex-vm-bridge diagnose
./bin/codex-vm-bridge prepare-base codex-tahoe-base
./bin/codex-vm-bridge clone --backend tart codex-tahoe-base codex-vm-computer-base
./bin/codex-vm-bridge start --backend tart codex-vm-computer-base --vnc
./bin/codex-vm-bridge install-agent --backend tart codex-vm-computer-base
```

Inside the VM, approve Screen Recording and Accessibility for the guest agent processes. Then stop the base:

```bash
./bin/codex-vm-bridge stop --backend tart codex-vm-computer-base
```

For actual work, clone from the prepared base:

```bash
./bin/codex-vm-bridge clone --backend tart codex-vm-computer-base task-vm
./bin/codex-vm-bridge start --backend tart task-vm --vnc --mount "repo:$PWD:tag=repo"
./bin/codex-vm-bridge ip --backend tart task-vm
```

Then use the guest agent:

```bash
./bin/codex-vm-bridge agent ping --host <guest-ip>
./bin/codex-vm-bridge agent screenshot --host <guest-ip> --output /tmp/vm.png
./bin/codex-vm-bridge agent ax-tree --host <guest-ip> --depth 5 --max-children 80
./bin/codex-vm-bridge agent ax-press --host <guest-ip> --id <element-id>
./bin/codex-vm-bridge agent ax-set-value --host <guest-ip> --id <element-id> --value "text"
```

Run terminal commands inside the VM:

```bash
./bin/codex-vm-bridge exec --backend tart task-vm zsh -lc 'cd /Volumes/My\ Shared\ Files/repo && xcodegen generate && xcodebuild -list'
```

When using Tart mounts, `--mount "repo:$PWD:tag=repo"` passes through to `tart run --dir`. macOS guests automount the share under `/Volumes/My Shared Files/repo`. Prefer this for repositories and large folders because the VM reads the host workspace directly.

For backends or workflows where mounting is unavailable, copy a file or folder into the VM:

```bash
./bin/codex-vm-bridge push --backend tart task-vm ./MyProject /Users/admin/MyProject
```

Provision the prepared base with common Apple development tools:

```bash
./bin/codex-vm-bridge start --backend tart codex-vm-computer-base
./bin/codex-vm-bridge provision-dev-tools --backend tart codex-vm-computer-base
./bin/codex-vm-bridge stop --backend tart codex-vm-computer-base
```

This installs Homebrew when missing, then installs `xcodegen`, `make`, `xcbeautify`, and `swiftformat`. It installs `swiftlint` only when full `/Applications/Xcode.app` is present; Homebrew cannot install current SwiftLint against Command Line Tools alone. It also verifies `xcodebuild`, `swift`, and `swiftc`; if full Xcode is missing, `xcodebuild` will report that limitation.

## Base Images

Prepared macOS base images are intentionally not shipped in this repository, npm package, GitHub Releases, or Hugging Face. Each machine must build and provision its own base image locally because the image contains Apple software, guest user state, privacy grants, package-manager caches, and potentially machine-specific data.

Agents should follow this rule:

1. Run `codex-vm-bridge diagnose`.
2. If `codex-vm-computer-base` exists, clone it for work.
3. If it does not exist, create it locally with `prepare-base`, `clone`, `install-agent`, and `provision-dev-tools`.
4. Ask the user to approve guest Screen Recording and Accessibility prompts when macOS requires it.
5. Never fetch, upload, publish, or redistribute a prepared macOS VM image.

## Computer Use Parity

Native Codex Computer Use is fast because it directly sees host pixels and the host accessibility tree. This bridge closes the practical gap by exposing the same kinds of primitives from inside the VM:

- `screenshot`: current guest pixels
- `ax-tree`: focused app/window semantic tree
- `ax-press`: press an element by traversal id
- `ax-click`: click an element center by traversal id
- `ax-set-value`: set text/value by traversal id
- `click`, `type`, `key`: fallback input

The remaining difference is transport and virtualization latency.

## MCP Server

Run:

```bash
./bin/codex-vm-bridge mcp
```

The MCP server exposes VM lifecycle tools, `vm_exec`, `vm_push`, and guest-agent tools such as `agent_ax_tree`, `agent_ax_press`, and `agent_ax_set_value`.

See [examples/mcp.json](examples/mcp.json).

## Codex Skill

The skill bundle is included at:

```text
skills/codex-vm-computer
```

Install it by copying that folder into your Codex skills directory:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
cp -R skills/codex-vm-computer "${CODEX_HOME:-$HOME/.codex}/skills/"
```

## Notes

- `codex-vm-computer-base` is a local Tart VM name, not a repository artifact.
- Apple does not allow normal userland code to silently grant Screen Recording. First-run approval must happen in the VM UI or through real MDM policy.
- UTM support exists, but Tart is the preferred backend for disposable macOS VM workflows.
