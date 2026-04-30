# Computer Use VM

Let agents run disposable VMs.
<img width="1706" height="922" alt="screnshot" src="https://github.com/user-attachments/assets/64746afc-22a9-4948-ab27-e6080b8955cd" />


Computer Use VM gives coding agents a VM they can use for terminal and GUI work instead of touching your host desktop. Start a disposable VM, mount the current project, let the agent work inside it, then throw the VM away.

It does not ship a macOS base image. Each machine builds its own base locally.

## Let Your Agent Install It

Copy this into your agent:

```md
Read https://raw.githubusercontent.com/ZimengXiong/computer-use-vm/main/INSTALL.md and follow it to install Computer Use VM. During first-time setup, tell me when I need to VNC into the VM to approve macOS Screen Recording and Accessibility permissions.
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
computer-use-vm install-agent computer-use-vm-base
computer-use-vm provision-dev-tools computer-use-vm-base
computer-use-vm stop computer-use-vm-base
```

For a task, clone the base and mount your repo:

```bash
computer-use-vm clone computer-use-vm-base task-vm
computer-use-vm start task-vm --mount "repo:$PWD:tag=repo"
computer-use-vm exec task-vm zsh -lc 'cd /Volumes/My\ Shared\ Files/repo && make test'
```

For GUI work, use the guest agent:

```bash
computer-use-vm agent screenshot --host <guest-ip> --output /tmp/vm.png
computer-use-vm agent ax-tree --host <guest-ip>
computer-use-vm agent type --host <guest-ip> --text "hello"
```

The skill gives agents the longer workflow details when they need them.

## MCP

```bash
computer-use-vm mcp
```

See [examples/mcp.json](examples/mcp.json).
