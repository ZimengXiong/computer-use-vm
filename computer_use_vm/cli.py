from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import sys
import time
import subprocess
import tempfile
from importlib.resources import files
from typing import Any

from .agent_client import AgentClient
from .backends import BridgeError, all_diagnostics, get_backend
from .mcp_server import serve_stdio


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GUEST_AGENT = str(files("computer_use_vm").joinpath("assets", "guest", "computer_use_vm_guest_agent.py"))
GUEST_HELPER = str(files("computer_use_vm").joinpath("assets", "guest", "ComputerUseVMGuestHelper.swift"))
VNCDO = os.path.join(ROOT, ".venv", "bin", "vncdo")
WEBSOCKIFY = os.path.join(ROOT, ".venv", "bin", "websockify")
NOVNC_DIR = os.path.join(ROOT, ".cache", "novnc")
LAUNCH_AGENT_LABEL_PREFIX = "local.computer-use.vm-agent"
LEGACY_LAUNCH_AGENT_LABELS = ["local.codex.vm-agent"]


def emit(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True))


def copy_skill() -> dict[str, Any]:
    source = os.path.join(ROOT, "skills", "computer-use-vm")
    skills_home = os.environ.get("SKILLS_HOME", os.path.join(os.path.expanduser("~"), ".agents"))
    target = os.path.join(skills_home, "skills", "computer-use-vm")
    if not os.path.isdir(source):
        raise BridgeError(f"skill source not found: {source}")
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))
    wrapper = os.path.join(target, "scripts", "computer-use-vm")
    with open(wrapper, "r", encoding="utf-8") as handle:
        text = handle.read()
    with open(wrapper, "w", encoding="utf-8") as handle:
        handle.write(text.replace("__COMPUTER_USE_VM_ROOT__", ROOT))
    os.chmod(wrapper, 0o755)
    return {
        "installed": True,
        "skill": "computer-use-vm",
        "target": target,
        "bridge_root": ROOT,
        "base_image_policy": "Each machine builds its own base locally. That keeps Apple software, privacy grants, user state, caches, and machine-specific data out of GitHub, npm, releases, and Hugging Face.",
        "next_steps": [
            "computer-use-vm diagnose",
            "computer-use-vm prepare-base computer-use-tahoe-base",
            "computer-use-vm clone computer-use-tahoe-base computer-use-vm-base",
            "computer-use-vm start computer-use-vm-base --vnc",
            "computer-use-vm install-agent computer-use-vm-base",
            "computer-use-vm provision-dev-tools computer-use-vm-base",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="computer-use-vm")
    parser.add_argument("--backend", choices=["tart", "utm"], help="VM backend; default prefers Tart then UTM")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("diagnose")
    sub.add_parser("mcp")
    sub.add_parser("install-skill")
    sub.add_parser("add")
    p = sub.add_parser("list")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)

    p = sub.add_parser("start")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("--visible", action="store_true")
    p.add_argument("--vnc", action="store_true")
    p.add_argument("--no-novnc", action="store_true", help="Do not launch a browser-viewable noVNC stream when --vnc is used")
    p.add_argument("--novnc-port", type=int, help="Preferred local noVNC web port; defaults to the first free port from 6080")
    p.add_argument("--disposable", action="store_true")
    p.add_argument("--mount", action="append", default=[], help="Tart directory share, passed to tart run --dir. Example: repo:$PWD:tag=repo")

    p = sub.add_parser("stop")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")

    p = sub.add_parser("clone")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("source")
    p.add_argument("name")

    p = sub.add_parser("prepare-base")
    p.add_argument("name", nargs="?", default="computer-use-tahoe-base")
    p.add_argument("--image", default="ghcr.io/cirruslabs/macos-tahoe-base:latest")

    p = sub.add_parser("delete")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")

    p = sub.add_parser("ip")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")

    p = sub.add_parser("exec")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("command", nargs=argparse.REMAINDER)

    p = sub.add_parser("push")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("local_path")
    p.add_argument("remote_path")

    p = sub.add_parser("provision-dev-tools")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")

    p = sub.add_parser("configure-guest")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("--admin-user", default="admin")

    p = sub.add_parser("install-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("--remote-dir", default="/Users/admin/computer-use-vm-agent")
    p.add_argument("--port", type=int, default=7042)

    p = sub.add_parser("start-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("--remote-dir", default="/Users/admin/computer-use-vm-agent")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=7042)

    p = sub.add_parser("stop-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")

    p = sub.add_parser("verify-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("--port", type=int, default=7042)
    p.add_argument("--host")

    p = sub.add_parser("agent")
    p.add_argument("action", choices=["ping", "permissions", "list-apps", "activate-app", "state", "snapshot", "screenshot", "ax-tree", "ax-press", "ax-click", "ax-set-value", "ax-action", "click", "drag", "scroll", "type", "key"])
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=7042)
    p.add_argument("--output")
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--button", default="left")
    p.add_argument("--click-count", type=int, default=1)
    p.add_argument("--text")
    p.add_argument("--key")
    p.add_argument("--modifier", action="append", default=[])
    p.add_argument("--app")
    p.add_argument("--action-name")
    p.add_argument("--direction")
    p.add_argument("--pages", type=float, default=1)
    p.add_argument("--from-x", type=int)
    p.add_argument("--from-y", type=int)
    p.add_argument("--to-x", type=int)
    p.add_argument("--to-y", type=int)
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--max-children", type=int, default=80)
    p.add_argument("--id", type=int)
    p.add_argument("--value")

    p = sub.add_parser("vnc")
    p.add_argument("action", choices=["screenshot", "click", "type", "key"])
    p.add_argument("--host", required=True)
    p.add_argument("--user", default="admin")
    p.add_argument("--password", default="admin")
    p.add_argument("--output")
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--button", default="1")
    p.add_argument("--text")
    p.add_argument("--key")

    p = sub.add_parser("vm-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("action", choices=["ping", "permissions", "list-apps", "activate-app", "state", "snapshot", "screenshot", "ax-tree", "ax-press", "ax-click", "ax-set-value", "ax-action", "click", "drag", "scroll", "type", "key"])
    p.add_argument("--port", type=int, default=7042)
    p.add_argument("--output")
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--button", default="left")
    p.add_argument("--click-count", type=int, default=1)
    p.add_argument("--text")
    p.add_argument("--key")
    p.add_argument("--modifier", action="append", default=[])
    p.add_argument("--app")
    p.add_argument("--action-name")
    p.add_argument("--direction")
    p.add_argument("--pages", type=float, default=1)
    p.add_argument("--from-x", type=int)
    p.add_argument("--from-y", type=int)
    p.add_argument("--to-x", type=int)
    p.add_argument("--to-y", type=int)
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--max-children", type=int, default=80)
    p.add_argument("--id", type=int)
    p.add_argument("--value")
    return parser


def launch_agent_label(port: int) -> str:
    return f"{LAUNCH_AGENT_LABEL_PREFIX}.{port}"


def launch_agent_path(port: int) -> str:
    return f"/Users/admin/Library/LaunchAgents/{launch_agent_label(port)}.plist"


def launch_agent_plist(remote_dir: str, port: int) -> str:
    label = launch_agent_label(port)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>{remote_dir}/computer_use_vm_guest_agent.py</string>
    <string>--host</string>
    <string>0.0.0.0</string>
    <string>--port</string>
    <string>{port}</string>
    <string>--helper</string>
    <string>{remote_dir}/computer-use-vm-guest-helper</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{remote_dir}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{remote_dir}/agent.log</string>
  <key>StandardErrorPath</key>
  <string>{remote_dir}/agent.err.log</string>
</dict>
</plist>
"""


def install_agent(vm: str, backend_name: str | None, remote_dir: str, port: int = 7042) -> dict[str, Any]:
    backend = get_backend(backend_name)
    backend.exec(vm, ["mkdir", "-p", remote_dir]).check()
    backend.push(vm, GUEST_AGENT, f"{remote_dir}/computer_use_vm_guest_agent.py")
    backend.push(vm, GUEST_HELPER, f"{remote_dir}/ComputerUseVMGuestHelper.swift")
    plist_local = None
    try:
        import tempfile

        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as handle:
            plist_local = handle.name
            handle.write(launch_agent_plist(remote_dir, port))
        backend.push(vm, plist_local, launch_agent_path(port))
    finally:
        if plist_local:
            try:
                os.unlink(plist_local)
            except OSError:
                pass
    compile_cmd = [
        "zsh",
        "-lc",
        f"cd {remote_dir!r} && swiftc -O ComputerUseVMGuestHelper.swift -o computer-use-vm-guest-helper && chmod +x computer-use-vm-guest-helper computer_use_vm_guest_agent.py && chmod 644 {launch_agent_path(port)!r}",
    ]
    compile_result = backend.exec(vm, compile_cmd).check()
    return {
        "backend": backend.name,
        "vm": vm,
        "remote_dir": remote_dir,
        "agent": f"{remote_dir}/computer_use_vm_guest_agent.py",
        "helper": f"{remote_dir}/computer-use-vm-guest-helper",
        "launch_agent": launch_agent_path(port),
        "launch_agent_label": launch_agent_label(port),
        "start_command": f"computer-use-vm start-agent {vm} --port {port}",
        "compile_stdout": compile_result.stdout,
        "compile_stderr": compile_result.stderr,
    }


def start_agent(vm: str, backend_name: str | None, remote_dir: str, host: str, port: int) -> dict[str, Any]:
    backend = get_backend(backend_name)
    label = launch_agent_label(port)
    path = launch_agent_path(port)
    plist = launch_agent_plist(remote_dir, port).replace("'", "'\\''")
    labels = " ".join([label, *LEGACY_LAUNCH_AGENT_LABELS])
    cmd = (
        "set -e; "
        "uid=$(id -u); "
        "mkdir -p /Users/admin/Library/LaunchAgents; "
        f"printf '%s' '{plist}' > {path!r}; "
        f"chmod 644 {path!r}; "
        f"for label in {labels}; do launchctl bootout gui/$uid/$label >/dev/null 2>&1 || true; done; "
        f"pids=$(lsof -tiTCP:{port} -sTCP:LISTEN 2>/dev/null || true); [ -n \"$pids\" ] && kill $pids >/dev/null 2>&1 || true; "
        f"launchctl bootstrap gui/$uid {path!r} >/dev/null 2>&1 || true; "
        f"launchctl kickstart -k gui/$uid/{label}; "
        f"launchctl print gui/$uid/{label} >/dev/null"
    )
    result = backend.exec(vm, ["sh", "-lc", cmd]).check()
    return {"backend": backend.name, "vm": vm, "started": True, "host": host, "port": port, "log": f"{remote_dir}/agent.log", "launch_agent": label, "stdout": result.stdout, "stderr": result.stderr}


def stop_agent(vm: str, backend_name: str | None) -> dict[str, Any]:
    backend = get_backend(backend_name)
    legacy = " ".join(LEGACY_LAUNCH_AGENT_LABELS)
    cmd = (
        "uid=$(id -u); "
        f"for label in $(launchctl list | awk '/{LAUNCH_AGENT_LABEL_PREFIX}/ {{print $3}}') {legacy}; do "
        "launchctl bootout gui/$uid/$label >/dev/null 2>&1 || true; "
        "done; "
        "pkill -f computer_use_vm_guest_agent.py || true"
    )
    result = backend.exec(vm, ["sh", "-lc", cmd]).check()
    return {"backend": backend.name, "vm": vm, "stopped": True, "stdout": result.stdout, "stderr": result.stderr}


def configure_guest(vm: str, backend_name: str | None, admin_user: str) -> dict[str, Any]:
    backend = get_backend(backend_name)
    script = f"""
set -euo pipefail
admin_user={admin_user!r}
sudo mkdir -p /etc/sudoers.d
printf '%s\\n' "$admin_user ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/99-computer-use-vm >/dev/null
sudo chmod 440 /etc/sudoers.d/99-computer-use-vm
sudo visudo -cf /etc/sudoers.d/99-computer-use-vm >/dev/null
sudo systemsetup -setsleep Never >/dev/null 2>&1 || true
sudo systemsetup -setdisplaysleep Never >/dev/null 2>&1 || true
sudo systemsetup -setcomputersleep Never >/dev/null 2>&1 || true
defaults write com.apple.screensaver idleTime 0 || true
mkdir -p "$HOME/Library/LaunchAgents" /Users/admin/computer-use-vm-agent
for plist in "$HOME"/Library/LaunchAgents/local.codex.vm-agent.plist; do
  [ -e "$plist" ] && rm -f "$plist"
done
uid=$(id -u)
launchctl bootout gui/$uid/local.codex.vm-agent >/dev/null 2>&1 || true
echo configured
"""
    result = backend.exec(vm, ["zsh", "-lc", script]).check()
    return {"backend": backend.name, "vm": vm, "configured": True, "stdout": result.stdout, "stderr": result.stderr}


def ensure_vnc_tools() -> None:
    needs_install = not os.path.exists(VNCDO) or not os.path.exists(WEBSOCKIFY)
    if not needs_install:
        probe = subprocess.run([VNCDO, "--help"], text=True, capture_output=True, timeout=30)
        ws_probe = subprocess.run([WEBSOCKIFY, "--help"], text=True, capture_output=True, timeout=30)
        needs_install = probe.returncode != 0 or ws_probe.returncode != 0
    if needs_install:
        shutil.rmtree(os.path.join(ROOT, ".venv"), ignore_errors=True)
        subprocess.run([sys.executable, "-m", "venv", os.path.join(ROOT, ".venv")], check=True)
        subprocess.run([os.path.join(ROOT, ".venv", "bin", "python"), "-m", "pip", "install", "-r", os.path.join(ROOT, "requirements-vnc.txt")], check=True)


def ensure_novnc() -> str:
    if os.path.isdir(os.path.join(NOVNC_DIR, ".git")):
        return NOVNC_DIR
    shutil.rmtree(NOVNC_DIR, ignore_errors=True)
    os.makedirs(os.path.dirname(NOVNC_DIR), exist_ok=True)
    git = shutil.which("git")
    if not git:
        raise BridgeError("git is required to install noVNC")
    subprocess.run([git, "clone", "--depth", "1", "https://github.com/novnc/noVNC.git", NOVNC_DIR], check=True)
    return NOVNC_DIR


def free_port(preferred: int = 6080) -> int:
    for port in range(preferred, preferred + 100):
        sock = socket.socket()
        try:
            sock.bind(("127.0.0.1", port))
            return port
        except OSError:
            continue
        finally:
            sock.close()
    raise BridgeError(f"no free local port found from {preferred}")


def wait_for_vm_ip(backend: Any, vm: str, timeout: int = 60) -> str:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            ips = backend.ip(vm)
            if ips:
                return ips[0]
        except Exception as exc:
            last_error = exc
        time.sleep(2)
    raise BridgeError(f"timed out waiting for IP address for {vm}: {last_error}")


def launch_novnc(vm: str, backend: Any, preferred_port: int | None = None) -> dict[str, Any]:
    ensure_vnc_tools()
    novnc = ensure_novnc()
    ip = wait_for_vm_ip(backend, vm)
    web_port = free_port(preferred_port or 6080)
    log_path = os.path.join(tempfile.gettempdir(), f"computer-use-vm-novnc-{vm}-{web_port}.log")
    log = open(log_path, "ab")
    proc = subprocess.Popen(
        [WEBSOCKIFY, "--web", novnc, f"127.0.0.1:{web_port}", f"{ip}:5900"],
        stdout=log,
        stderr=log,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    url = f"http://127.0.0.1:{web_port}/vnc.html?host=127.0.0.1&port={web_port}&autoconnect=true&resize=scale"
    return {
        "enabled": True,
        "vm": vm,
        "guest_vnc": f"{ip}:5900",
        "web_port": web_port,
        "url": url,
        "pid": proc.pid,
        "log": log_path,
        "note": "noVNC is for user-visible browser streaming; keep automation control through the guest agent or computer-use-vm vnc commands.",
    }


def provision_dev_tools(vm: str, backend_name: str | None) -> dict[str, Any]:
    backend = get_backend(backend_name)
    script = r"""
set -euo pipefail

if ! xcode-select -p >/dev/null 2>&1; then
  echo "Xcode Command Line Tools are not selected. Install them in the guest UI with: xcode-select --install" >&2
  exit 2
fi

if ! command -v brew >/dev/null 2>&1; then
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi

if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -x /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

brew update
for formula in xcodegen make xcbeautify swiftformat; do
  brew list --formula "$formula" >/dev/null 2>&1 || brew install "$formula"
done

swiftlint_status="not-attempted"
if [ -d /Applications/Xcode.app ]; then
  brew list --formula swiftlint >/dev/null 2>&1 || brew install swiftlint
  swiftlint_status="installed"
else
  swiftlint_status="skipped: requires full /Applications/Xcode.app, not just Command Line Tools"
fi
export swiftlint_status

python3 - <<'PY'
import json, os, shutil, subprocess
tools = ["xcodebuild", "swift", "swiftc", "xcodegen", "make", "xcbeautify", "swiftformat", "swiftlint", "brew"]
result = {"_notes": {"swiftlint": os.environ.get("swiftlint_status", "")}}
for tool in tools:
    path = shutil.which(tool)
    item = {"path": path}
    if path:
        try:
            proc = subprocess.run([tool, "--version"], text=True, capture_output=True, timeout=30)
            item["version"] = (proc.stdout or proc.stderr).splitlines()[0] if (proc.stdout or proc.stderr) else ""
        except Exception as exc:
            item["version_error"] = str(exc)
    result[tool] = item
print("COMPUTER_USE_VM_TOOLS_JSON_START")
print(json.dumps(result, indent=2, sort_keys=True))
PY
"""
    result = backend.exec(vm, ["zsh", "-lc", script]).check()
    marker = "COMPUTER_USE_VM_TOOLS_JSON_START\n"
    summary_text = result.stdout.split(marker, 1)[1] if marker in result.stdout else "{}"
    summary = json.loads(summary_text)
    return {"backend": backend.name, "vm": vm, "tools": summary, "stderr": result.stderr}


def verify_agent(vm: str, backend_name: str | None, host: str | None, port: int) -> dict[str, Any]:
    backend = get_backend(backend_name)
    ips = [host] if host else backend.ip(vm)
    if not ips:
        raise BridgeError(f"no IP address found for VM {vm}")
    errors = []
    for ip in ips:
        client = AgentClient(ip, port, timeout=10)
        try:
            ping = client.ping()
            permissions = client.permissions()
            screenshot = client.screenshot()
            tree = client.ax_tree(depth=2, max_children=20)
            return {
                "backend": backend.name,
                "vm": vm,
                "host": ip,
                "port": port,
                "ok": True,
                "ping": ping,
                "permissions": permissions,
                "screenshot": {k: v for k, v in screenshot.items() if k != "png_base64"},
                "ax_tree": {"app": tree.get("app"), "node_count": tree.get("node_count")},
            }
        except Exception as exc:
            errors.append({"host": ip, "error": str(exc)})
    return {
        "backend": backend.name,
        "vm": vm,
        "port": port,
        "ok": False,
        "errors": errors,
        "next_step": "Start the VM with --vnc and approve Screen Recording and Accessibility for /Users/admin/computer-use-vm-agent/computer-use-vm-guest-helper, then rerun verify-agent.",
    }


def run_agent_command(args: argparse.Namespace) -> dict[str, Any]:
    client = AgentClient(args.host, args.port)
    if args.action == "ping":
        return client.ping()
    if args.action == "permissions":
        return client.permissions()
    if args.action == "list-apps":
        return client.list_apps()
    if args.action == "activate-app":
        if args.app is None:
            raise BridgeError("agent activate-app requires --app")
        return client.activate_app(args.app)
    if args.action == "state":
        return client.state(args.depth, args.max_children, args.app)
    if args.action == "snapshot":
        return client.snapshot(args.app)
    if args.action == "screenshot":
        return client.screenshot(args.output)
    if args.action == "ax-tree":
        return client.ax_tree(args.depth, args.max_children, args.app)
    if args.action == "ax-press":
        if args.id is None:
            raise BridgeError("agent ax-press requires --id")
        return client.ax_press(args.id, args.depth, args.max_children, args.app)
    if args.action == "ax-click":
        if args.id is None:
            raise BridgeError("agent ax-click requires --id")
        return client.ax_click(args.id, args.depth, args.max_children, args.app)
    if args.action == "ax-set-value":
        if args.id is None or args.value is None:
            raise BridgeError("agent ax-set-value requires --id and --value")
        return client.ax_set_value(args.id, args.value, args.depth, args.max_children, args.app)
    if args.action == "ax-action":
        if args.id is None or args.action_name is None:
            raise BridgeError("agent ax-action requires --id and --action-name")
        return client.ax_action(args.id, args.action_name, args.depth, args.max_children, args.app)
    if args.action == "click":
        if args.x is None or args.y is None:
            raise BridgeError("agent click requires --x and --y")
        return client.click(args.x, args.y, args.button, args.click_count)
    if args.action == "drag":
        if args.from_x is None or args.from_y is None or args.to_x is None or args.to_y is None:
            raise BridgeError("agent drag requires --from-x --from-y --to-x --to-y")
        return client.drag(args.from_x, args.from_y, args.to_x, args.to_y)
    if args.action == "scroll":
        if args.direction is None:
            raise BridgeError("agent scroll requires --direction")
        return client.scroll(args.direction, args.pages, args.id, args.depth, args.max_children, args.app)
    if args.action == "type":
        if args.text is None:
            raise BridgeError("agent type requires --text")
        return client.type_text(args.text)
    if args.action == "key":
        if args.key is None:
            raise BridgeError("agent key requires --key")
        return client.key(args.key, args.modifier)
    raise BridgeError(f"unknown agent action {args.action}")


def run_vm_agent_command(args: argparse.Namespace) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    path = f"/{args.action}"
    if args.action in {"ping", "permissions", "list-apps", "screenshot"}:
        path = f"/{args.action}"
    elif args.action == "activate-app":
        if args.app is None:
            raise BridgeError("vm-agent activate-app requires --app")
        payload = {"app": args.app}
    elif args.action == "state":
        payload = {"depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "snapshot":
        if args.app:
            path = "/state"
            payload = {"depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "screenshot":
        path = "/screenshot"
    elif args.action == "ax-tree":
        path = "/ax-tree"
        payload = {"depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "ax-press":
        if args.id is None:
            raise BridgeError("vm-agent ax-press requires --id")
        path = "/ax-press"
        payload = {"id": args.id, "depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "ax-click":
        if args.id is None:
            raise BridgeError("vm-agent ax-click requires --id")
        path = "/ax-click"
        payload = {"id": args.id, "depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "ax-set-value":
        if args.id is None or args.value is None:
            raise BridgeError("vm-agent ax-set-value requires --id and --value")
        path = "/ax-set-value"
        payload = {"id": args.id, "value": args.value, "depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "ax-action":
        if args.id is None or args.action_name is None:
            raise BridgeError("vm-agent ax-action requires --id and --action-name")
        payload = {"id": args.id, "action": args.action_name, "depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "click":
        if args.x is None or args.y is None:
            raise BridgeError("vm-agent click requires --x and --y")
        payload = {"x": args.x, "y": args.y, "button": args.button, "click_count": args.click_count}
    elif args.action == "drag":
        if args.from_x is None or args.from_y is None or args.to_x is None or args.to_y is None:
            raise BridgeError("vm-agent drag requires --from-x --from-y --to-x --to-y")
        payload = {"from_x": args.from_x, "from_y": args.from_y, "to_x": args.to_x, "to_y": args.to_y}
    elif args.action == "scroll":
        if args.direction is None:
            raise BridgeError("vm-agent scroll requires --direction")
        payload = {"direction": args.direction, "pages": args.pages, "id": args.id, "depth": args.depth, "max_children": args.max_children, "app": args.app}
    elif args.action == "type":
        if args.text is None:
            raise BridgeError("vm-agent type requires --text")
        payload = {"text": args.text}
    elif args.action == "key":
        if args.key is None:
            raise BridgeError("vm-agent key requires --key")
        payload = {"key": args.key, "modifiers": args.modifier}

    script = r"""
import json, sys, urllib.request
port = int(sys.argv[1])
path = sys.argv[2]
payload = json.loads(sys.argv[3])
data = None
headers = {}
if payload:
    data = json.dumps(payload).encode()
    headers["Content-Type"] = "application/json"
req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=headers)
print(urllib.request.urlopen(req, timeout=60).read().decode())
"""
    backend = get_backend(args.backend)
    result = backend.exec(args.vm, ["python3", "-c", script, str(args.port), path, json.dumps(payload)]).check()
    data = json.loads(result.stdout or "{}")
    if args.action == "screenshot" and args.output and "png_base64" in data:
        with open(args.output, "wb") as handle:
            handle.write(base64.b64decode(data["png_base64"]))
        data = {k: v for k, v in data.items() if k != "png_base64"}
        data["output"] = args.output
    return data


def run_vnc_command(args: argparse.Namespace) -> dict[str, Any]:
    ensure_vnc_tools()
    if not os.path.exists(VNCDO):
        raise BridgeError(f"vncdotool is not installed at {VNCDO}; run: python3 -m venv {ROOT}/.venv && {ROOT}/.venv/bin/pip install vncdotool")
    base = [VNCDO, "-s", args.host, "-u", args.user, "-p", args.password, "--timeout", "30"]
    if args.action == "screenshot":
        if not args.output:
            raise BridgeError("vnc screenshot requires --output")
        cmd = [*base, "capture", args.output]
    elif args.action == "click":
        if args.x is None or args.y is None:
            raise BridgeError("vnc click requires --x and --y")
        cmd = [*base, "move", str(args.x), str(args.y), "click", args.button]
    elif args.action == "type":
        if args.text is None:
            raise BridgeError("vnc type requires --text")
        cmd = [*base, "type", args.text]
    elif args.action == "key":
        if args.key is None:
            raise BridgeError("vnc key requires --key")
        cmd = [*base, "key", args.key]
    else:
        raise BridgeError(f"unknown vnc action {args.action}")
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise BridgeError(f"vnc command failed ({proc.returncode}): {proc.stderr or proc.stdout}")
    result = {"ok": True, "action": args.action, "host": args.host}
    if args.action == "screenshot":
        result["output"] = args.output
    return result


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "diagnose":
            emit(all_diagnostics())
            return 0
        if args.cmd == "mcp":
            serve_stdio()
            return 0
        if args.cmd in {"install-skill", "add"}:
            emit(copy_skill())
            return 0
        backend = get_backend(args.backend)
        if args.cmd == "list":
            emit(backend.list())
        elif args.cmd == "start":
            result = backend.start(args.vm, headless=not args.visible and not args.vnc, disposable=args.disposable, vnc=args.vnc, mounts=args.mount)
            if args.vnc and not args.no_novnc:
                try:
                    result["novnc"] = launch_novnc(args.vm, backend, args.novnc_port)
                except Exception as exc:
                    result["novnc"] = {
                        "enabled": False,
                        "error": str(exc),
                        "note": "The VM VNC server was started, but the browser-viewable noVNC stream could not be launched.",
                    }
            emit(result)
        elif args.cmd == "stop":
            emit(backend.stop(args.vm))
        elif args.cmd == "clone":
            emit(backend.clone(args.source, args.name))
        elif args.cmd == "prepare-base":
            tart = get_backend("tart")
            if not hasattr(tart, "clone_public_base"):
                raise BridgeError("prepare-base requires Tart")
            emit(tart.clone_public_base(args.name, args.image))  # type: ignore[attr-defined]
        elif args.cmd == "delete":
            emit(backend.delete(args.vm))
        elif args.cmd == "ip":
            emit(backend.ip(args.vm))
        elif args.cmd == "exec":
            if not args.command:
                raise BridgeError("exec requires a command after the VM name")
            result = backend.exec(args.vm, args.command)
            emit({"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
            return result.returncode
        elif args.cmd == "push":
            emit(backend.push(args.vm, args.local_path, args.remote_path))
        elif args.cmd == "provision-dev-tools":
            emit(provision_dev_tools(args.vm, args.backend))
        elif args.cmd == "configure-guest":
            emit(configure_guest(args.vm, args.backend, args.admin_user))
        elif args.cmd == "install-agent":
            emit(install_agent(args.vm, args.backend, args.remote_dir, args.port))
        elif args.cmd == "start-agent":
            emit(start_agent(args.vm, args.backend, args.remote_dir, args.host, args.port))
        elif args.cmd == "stop-agent":
            emit(stop_agent(args.vm, args.backend))
        elif args.cmd == "verify-agent":
            emit(verify_agent(args.vm, args.backend, args.host, args.port))
        elif args.cmd == "agent":
            emit(run_agent_command(args))
        elif args.cmd == "vnc":
            emit(run_vnc_command(args))
        elif args.cmd == "vm-agent":
            emit(run_vm_agent_command(args))
        else:
            parser.error(f"unknown command {args.cmd}")
    except Exception as exc:
        print(f"computer-use-vm: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
