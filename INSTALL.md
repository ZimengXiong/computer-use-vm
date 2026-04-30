# Install Computer Use VM

Install the skill with the open skills CLI:

```bash
npx skills add ZimengXiong/computer-use-vm
```

Install the command on PATH:

```bash
npm install -g computer-use-vm
computer-use-vm diagnose
```

If you do not want a global install, agents can run the command through `npx -y computer-use-vm ...`, but a global install is simpler and avoids PATH discovery issues.

Install the VM backend you want to use separately. Tart is the recommended path on Apple Silicon Macs:

```bash
brew install cirruslabs/cli/tart
```

> [!NOTE]
> First-time setup is not fully unattended. The user needs to VNC into the VM once to approve macOS Screen Recording and Accessibility prompts for the guest agent/helper.

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

After that, agents can clone `computer-use-vm-base` for disposable work.
