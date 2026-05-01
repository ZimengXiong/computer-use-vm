# Computer Use VM

Let agents run disposable, headless macOS VMs. No more window switching and having to accomdate another 'person' using your computer.

Here's codex in a verification loop debugging my obsidian terminal extension, all without interrupting my user space:
<img width="1848" height="5983" alt="image" src="https://github.com/user-attachments/assets/b3914155-ba99-4815-bb35-630208199eb0" />


Computer Use VM gives coding agents a VM they can use for terminal and GUI work instead of touching your host desktop. Start a disposable VM, mount the current project, let the agent work inside it, then throw the VM away.

It does not ship a macOS base image. Each machine builds its own base locally.

## Let Your Agent Install It

Copy this into your agent:

```md
Read https://raw.githubusercontent.com/ZimengXiong/computer-use-vm/main/INSTALL.md and follow it to install Computer Use VM. Make sure the `computer-use-vm` command is installed on PATH, then run `computer-use-vm diagnose`. During first-time setup, tell me when I need to VNC into the VM to approve macOS Screen Recording and Accessibility permissions and set things up, and save that as the base for other VMs in the future.
```

> [!NOTE]
> First-time setup is not fully unattended. The user needs to VNC into the VM once to approve macOS Screen Recording and Accessibility prompts for the guest agent/helper.

## Use

Build a local base once:

```bash
computer-use-vm diagnose
computer-use-vm prepare-base
computer-use-vm clone computer-use-tahoe-base computer-use-vm-base
computer-use-vm start computer-use-vm-base --vnc
computer-use-vm configure-guest computer-use-vm-base
computer-use-vm install-agent computer-use-vm-base
computer-use-vm start-agent computer-use-vm-base
computer-use-vm verify-agent computer-use-vm-base
computer-use-vm provision-dev-tools computer-use-vm-base
computer-use-vm stop computer-use-vm-base
```

`configure-guest` makes the VM agent-friendly: passwordless sudo for the admin user, sleep disabled, and stale old agents removed. `verify-agent` is the gate for a reusable base image. It checks the guest agent, Screen Recording, Accessibility, screenshots, and AX-tree access. If it fails, approve the macOS privacy prompts in the guest over VNC, then rerun `start-agent` and `verify-agent`. Once it passes, stop this VM and clone it for tasks.

For a task, clone the base and mount your repo:

```bash
computer-use-vm clone computer-use-vm-base task-vm
computer-use-vm start task-vm --vnc --mount "repo:$PWD:tag=repo"
computer-use-vm exec task-vm zsh -lc 'cd /Volumes/My\ Shared\ Files/repo && make test'
```

When `--vnc` is used, the output includes a browser URL for watching the VM.

For GUI work, use the guest agent:

```bash
computer-use-vm agent list-apps --host <guest-ip>
computer-use-vm agent state --host <guest-ip> --app Safari
computer-use-vm agent screenshot --host <guest-ip> --output /tmp/vm.png
computer-use-vm agent ax-tree --host <guest-ip> --app Safari
computer-use-vm agent ax-action --host <guest-ip> --app Safari --id <element-id> --action-name AXShowMenu
computer-use-vm agent scroll --host <guest-ip> --app Safari --direction down --pages 1
computer-use-vm agent drag --host <guest-ip> --from-x 200 --from-y 180 --to-x 400 --to-y 180
computer-use-vm agent type --host <guest-ip> --text "hello"
computer-use-vm agent key --host <guest-ip> --key Return
```

The skill gives agents the longer workflow details when they need them.

## MCP

```bash
computer-use-vm mcp
```

See [examples/mcp.json](examples/mcp.json).
