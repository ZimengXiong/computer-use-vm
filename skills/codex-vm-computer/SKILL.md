---
name: codex-vm-computer
description: Run computer-use and GUI automation work inside an isolated macOS VM instead of the host desktop. Use when Codex needs to test macOS apps, browse or click around without blocking the native system, run risky installers, perform background GUI tasks, inspect a VM screen, or manage disposable Tart/UTM virtual machines with a guest-side screenshot/click/type agent.
---

# Codex VM Computer

Use the local bridge through `codex-vm-bridge` or the installed skill wrapper at `scripts/codex-vm-bridge` to control disposable macOS VMs.

## Base Image Policy

Prepared macOS VM base images are not distributed by this skill and must not be downloaded, uploaded, published, or redistributed by agents. Build and provision a local base image on each machine. A prepared base may contain Apple software, guest user state, privacy grants, package-manager caches, and machine-specific data.

If `codex-vm-computer-base` is missing, create it locally with the commands in this skill. If macOS privacy prompts appear inside the guest, ask the user to approve Screen Recording and Accessibility for the guest agent/helper. Do not work around those prompts by fetching a prebuilt base image.

## Default Workflow

1. Run diagnostics:

```bash
codex-vm-bridge diagnose
```

2. Prefer Tart for headless/background runs. Use UTM when an existing UTM VM is the target.

3. Prefer the prepared base image:

```bash
codex-vm-bridge clone codex-vm-computer-base <task-vm>
```

This base has the guest agent installed as a user LaunchAgent and has the required macOS privacy grants for native screenshots.

4. Prepare a raw Tart base image only if `codex-vm-computer-base` does not exist. Build this locally; do not fetch a prepared macOS base image:

```bash
codex-vm-bridge prepare-base codex-tahoe-base
codex-vm-bridge clone codex-tahoe-base codex-vm-computer-base
codex-vm-bridge start codex-vm-computer-base --vnc
codex-vm-bridge install-agent codex-vm-computer-base
codex-vm-bridge provision-dev-tools codex-vm-computer-base
codex-vm-bridge stop codex-vm-computer-base
```

5. Use clone/delete isolation when a base image exists:

```bash
codex-vm-bridge clone <base-vm> <task-vm>
codex-vm-bridge start <task-vm> --mount "repo:$PWD:tag=repo"
codex-vm-bridge ip <task-vm>
```

For host workspace access, prefer Tart directory mounts over copying:

```bash
codex-vm-bridge start <task-vm> --mount "repo:$PWD:tag=repo"
codex-vm-bridge exec <task-vm> zsh -lc 'cd /Volumes/My\ Shared\ Files/repo && pwd && ls'
```

macOS guests automount the shared directory under `/Volumes/My Shared Files/repo`. Use `push` only when a mount is unavailable or the VM is already running without the needed share:

```bash
codex-vm-bridge push <task-vm> ./local-file-or-folder /Users/admin/local-file-or-folder
```

The prepared base should already have Homebrew, XcodeGen, Make, xcbeautify, and swiftformat. If a base is missing those tools, start it and run:

```bash
codex-vm-bridge provision-dev-tools codex-vm-computer-base
```

Full `xcodebuild` and SwiftLint require full `/Applications/Xcode.app`; Command Line Tools alone are not enough for those checks.

6. Install the guest agent only for raw or unprepared VMs:

```bash
codex-vm-bridge install-agent <task-vm>
```

7. Start the agent inside the guest only for raw or unprepared VMs:

```bash
codex-vm-bridge start-agent <task-vm>
```

8. Drive the VM through the agent:

```bash
codex-vm-bridge agent ping --host <guest-ip>
codex-vm-bridge agent screenshot --host <guest-ip> --output /tmp/vm.png
codex-vm-bridge agent ax-tree --host <guest-ip> --depth 5 --max-children 80
codex-vm-bridge agent ax-press --host <guest-ip> --id <element-id>
codex-vm-bridge agent ax-click --host <guest-ip> --id <element-id>
codex-vm-bridge agent ax-set-value --host <guest-ip> --id <element-id> --value "text"
codex-vm-bridge agent click --host <guest-ip> --x 200 --y 180
codex-vm-bridge agent type --host <guest-ip> --text "hello"
```

Prefer AX actions over coordinate actions when an element id is available. Use `ax-tree` first, choose an element by role/title/description/frame, then use `ax-press`, `ax-click`, or `ax-set-value` with the same depth/max-children parameters.

If guest networking or macOS privacy permissions block direct screenshots, start the VM with `--vnc` and use the VNC fallback:

```bash
codex-vm-bridge vnc screenshot --host <guest-ip> --output /tmp/vm.png
codex-vm-bridge vnc click --host <guest-ip> --x 200 --y 180
codex-vm-bridge vnc type --host <guest-ip> --text "hello"
```

9. Stop and delete task clones after use unless the user requested persistence.

## Modes

- Headless/background: `start` defaults to hidden/no-graphics where the backend supports it. Use this for shell/background work; pixel screenshots are not available without a display surface.
- Visible/introspection: pass `--visible` to show the VM window, or `--vnc` to expose a VNC screen-sharing session.
- Disposable UTM run: pass `--disposable` for UTM snapshot-style runs.
- Tart disposable run: clone from a base VM, work in the clone, then delete the clone.

## MCP Server

Expose bridge tools over stdio with:

```bash
codex-vm-bridge mcp
```

Available tools include VM diagnostics, list, start with Tart mounts, stop, clone, delete, IP lookup, `vm_exec`, `vm_push`, guest-agent start/stop, and guest-agent snapshot/AX-tree/AX actions/click/type.

## Important Constraints

- The fastest path is the in-guest agent because screenshots, AX-tree introspection, and input are native to the VM.
- VNC/SPICE/UTM window automation is fallback only; it is useful for bootstrap, visual debugging, and pre-permission introspection but adds latency and coordinate fragility.
- macOS privacy prompts may require granting Screen Recording and Accessibility permissions inside the guest.
- Do not ship, fetch, upload, or redistribute prepared macOS VM images. Always build the base locally.
- UTM `utmctl` can fail from non-GUI sessions with Apple Event permission errors; use Tart when host-level GUI scripting permissions are unavailable.
