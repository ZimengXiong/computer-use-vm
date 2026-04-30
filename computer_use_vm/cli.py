from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import sys
import subprocess
from importlib.resources import files
from typing import Any

from .agent_client import AgentClient
from .backends import BridgeError, all_diagnostics, get_backend
from .mcp_server import serve_stdio


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
GUEST_AGENT = str(files("computer_use_vm").joinpath("assets", "guest", "computer_use_vm_guest_agent.py"))
GUEST_HELPER = str(files("computer_use_vm").joinpath("assets", "guest", "ComputerUseVMGuestHelper.swift"))
VNCDO = os.path.join(ROOT, ".venv", "bin", "vncdo")


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

    p = sub.add_parser("install-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("--remote-dir", default="/Users/admin/computer-use-vm-agent")

    p = sub.add_parser("start-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")
    p.add_argument("--remote-dir", default="/Users/admin/computer-use-vm-agent")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=7042)

    p = sub.add_parser("stop-agent")
    p.add_argument("--backend", choices=["tart", "utm"], help=argparse.SUPPRESS)
    p.add_argument("vm")

    p = sub.add_parser("agent")
    p.add_argument("action", choices=["ping", "snapshot", "screenshot", "ax-tree", "ax-press", "ax-click", "ax-set-value", "click", "type", "key"])
    p.add_argument("--host", required=True)
    p.add_argument("--port", type=int, default=7042)
    p.add_argument("--output")
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--button", default="left")
    p.add_argument("--text")
    p.add_argument("--key")
    p.add_argument("--modifier", action="append", default=[])
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
    p.add_argument("action", choices=["ping", "snapshot", "screenshot", "ax-tree", "ax-press", "ax-click", "ax-set-value", "click", "type", "key"])
    p.add_argument("--port", type=int, default=7042)
    p.add_argument("--output")
    p.add_argument("--x", type=int)
    p.add_argument("--y", type=int)
    p.add_argument("--button", default="left")
    p.add_argument("--text")
    p.add_argument("--key")
    p.add_argument("--modifier", action="append", default=[])
    p.add_argument("--depth", type=int, default=5)
    p.add_argument("--max-children", type=int, default=80)
    p.add_argument("--id", type=int)
    p.add_argument("--value")
    return parser


def install_agent(vm: str, backend_name: str | None, remote_dir: str) -> dict[str, Any]:
    backend = get_backend(backend_name)
    backend.exec(vm, ["mkdir", "-p", remote_dir]).check()
    backend.push(vm, GUEST_AGENT, f"{remote_dir}/computer_use_vm_guest_agent.py")
    backend.push(vm, GUEST_HELPER, f"{remote_dir}/ComputerUseVMGuestHelper.swift")
    compile_cmd = [
        "zsh",
        "-lc",
        f"cd {remote_dir!r} && swiftc -O ComputerUseVMGuestHelper.swift -o computer-use-vm-guest-helper && chmod +x computer-use-vm-guest-helper",
    ]
    compile_result = backend.exec(vm, compile_cmd).check()
    return {
        "backend": backend.name,
        "vm": vm,
        "remote_dir": remote_dir,
        "agent": f"{remote_dir}/computer_use_vm_guest_agent.py",
        "helper": f"{remote_dir}/computer-use-vm-guest-helper",
        "start_command": f"cd {remote_dir} && ./computer-use-vm-guest-helper permissions && python3 computer_use_vm_guest_agent.py --host 0.0.0.0 --port 7042 --helper ./computer-use-vm-guest-helper",
        "compile_stdout": compile_result.stdout,
        "compile_stderr": compile_result.stderr,
    }


def start_agent(vm: str, backend_name: str | None, remote_dir: str, host: str, port: int) -> dict[str, Any]:
    backend = get_backend(backend_name)
    cmd = (
        f"cd {remote_dir!r}; "
        "nohup python3 computer_use_vm_guest_agent.py "
        f"--host {host!r} --port {port} --helper ./computer-use-vm-guest-helper "
        "</dev/null >agent.log 2>&1 & printf '%s\\n' $!"
    )
    result = backend.exec(vm, ["sh", "-lc", cmd]).check()
    return {"backend": backend.name, "vm": vm, "pid": result.stdout.strip(), "host": host, "port": port, "log": f"{remote_dir}/agent.log"}


def stop_agent(vm: str, backend_name: str | None) -> dict[str, Any]:
    backend = get_backend(backend_name)
    result = backend.exec(vm, ["sh", "-lc", "pkill -f computer_use_vm_guest_agent.py || true"]).check()
    return {"backend": backend.name, "vm": vm, "stopped": True, "stdout": result.stdout, "stderr": result.stderr}


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


def run_agent_command(args: argparse.Namespace) -> dict[str, Any]:
    client = AgentClient(args.host, args.port)
    if args.action == "ping":
        return client.ping()
    if args.action == "snapshot":
        return client.snapshot()
    if args.action == "screenshot":
        return client.screenshot(args.output)
    if args.action == "ax-tree":
        return client.ax_tree(args.depth, args.max_children)
    if args.action == "ax-press":
        if args.id is None:
            raise BridgeError("agent ax-press requires --id")
        return client.ax_press(args.id, args.depth, args.max_children)
    if args.action == "ax-click":
        if args.id is None:
            raise BridgeError("agent ax-click requires --id")
        return client.ax_click(args.id, args.depth, args.max_children)
    if args.action == "ax-set-value":
        if args.id is None or args.value is None:
            raise BridgeError("agent ax-set-value requires --id and --value")
        return client.ax_set_value(args.id, args.value, args.depth, args.max_children)
    if args.action == "click":
        if args.x is None or args.y is None:
            raise BridgeError("agent click requires --x and --y")
        return client.click(args.x, args.y, args.button)
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
    if args.action == "screenshot":
        path = "/screenshot"
    elif args.action == "ax-tree":
        path = "/ax-tree"
        payload = {"depth": args.depth, "max_children": args.max_children}
    elif args.action == "ax-press":
        if args.id is None:
            raise BridgeError("vm-agent ax-press requires --id")
        path = "/ax-press"
        payload = {"id": args.id, "depth": args.depth, "max_children": args.max_children}
    elif args.action == "ax-click":
        if args.id is None:
            raise BridgeError("vm-agent ax-click requires --id")
        path = "/ax-click"
        payload = {"id": args.id, "depth": args.depth, "max_children": args.max_children}
    elif args.action == "ax-set-value":
        if args.id is None or args.value is None:
            raise BridgeError("vm-agent ax-set-value requires --id and --value")
        path = "/ax-set-value"
        payload = {"id": args.id, "value": args.value, "depth": args.depth, "max_children": args.max_children}
    elif args.action == "click":
        if args.x is None or args.y is None:
            raise BridgeError("vm-agent click requires --x and --y")
        payload = {"x": args.x, "y": args.y, "button": args.button}
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
            emit(backend.start(args.vm, headless=not args.visible and not args.vnc, disposable=args.disposable, vnc=args.vnc, mounts=args.mount))
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
        elif args.cmd == "install-agent":
            emit(install_agent(args.vm, args.backend, args.remote_dir))
        elif args.cmd == "start-agent":
            emit(start_agent(args.vm, args.backend, args.remote_dir, args.host, args.port))
        elif args.cmd == "stop-agent":
            emit(stop_agent(args.vm, args.backend))
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
