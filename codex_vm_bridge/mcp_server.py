from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .agent_client import AgentClient
from .backends import all_diagnostics, get_backend


def tool_schema() -> list[dict[str, Any]]:
    return [
        {"name": "vm_diagnose", "description": "Report local VM bridge backend availability and permission diagnostics.", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "vm_list", "description": "List VMs from Tart or UTM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}}}},
        {"name": "vm_start", "description": "Start a VM in headless/hidden mode by default, or VNC/visible mode for screen introspection. Tart supports directory shares through mounts, passed directly to tart run --dir.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "visible": {"type": "boolean"}, "vnc": {"type": "boolean"}, "disposable": {"type": "boolean"}, "mounts": {"type": "array", "items": {"type": "string"}}}, "required": ["vm"]}},
        {"name": "vm_stop", "description": "Stop a VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_clone", "description": "Clone a source VM to a named working VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "source": {"type": "string"}, "name": {"type": "string"}}, "required": ["source", "name"]}},
        {"name": "vm_prepare_base", "description": "Clone the public Cirrus macOS Tahoe Tart base image into a local base VM.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "default": "codex-tahoe-base"}, "image": {"type": "string", "default": "ghcr.io/cirruslabs/macos-tahoe-base:latest"}}}},
        {"name": "vm_delete", "description": "Delete a VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_ip", "description": "Return known IP addresses for a VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_exec", "description": "Run a terminal command inside a VM. Pass argv for direct execution, or command for a shell command run via zsh -lc.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "argv": {"type": "array", "items": {"type": "string"}}, "command": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_push", "description": "Copy a host file or directory into a VM. Prefer Tart mounts on vm_start for large workspaces.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "local_path": {"type": "string"}, "remote_path": {"type": "string"}}, "required": ["vm", "local_path", "remote_path"]}},
        {"name": "vm_start_agent", "description": "Start the installed in-guest HTTP computer-use agent.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "remote_dir": {"type": "string", "default": "/Users/admin/codex-vm-agent"}, "host": {"type": "string", "default": "0.0.0.0"}, "port": {"type": "integer", "default": 7042}}, "required": ["vm"]}},
        {"name": "vm_stop_agent", "description": "Stop the installed in-guest HTTP computer-use agent.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "agent_snapshot", "description": "Return guest screen metadata and screenshot base64 from the in-guest agent.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}}, "required": ["host"]}},
        {"name": "agent_ax_tree", "description": "Return the focused guest app/window accessibility tree with element roles, labels, bounds, and actions.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host"]}},
        {"name": "agent_ax_press", "description": "Perform AXPress on an element id from the latest equivalent AX tree traversal.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "id": {"type": "integer"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "id"]}},
        {"name": "agent_ax_click", "description": "Click the center of an element id from the latest equivalent AX tree traversal.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "id": {"type": "integer"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "id"]}},
        {"name": "agent_ax_set_value", "description": "Set an accessibility element value by id, falling back to focus and paste.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "id": {"type": "integer"}, "value": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "id", "value"]}},
        {"name": "agent_click", "description": "Click guest screen coordinates through the in-guest agent.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "default": "left"}}, "required": ["host", "x", "y"]}},
        {"name": "agent_type", "description": "Type text in the guest through the in-guest agent.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "text": {"type": "string"}}, "required": ["host", "text"]}},
    ]


def start_guest_agent(vm: str, backend_name: str | None, remote_dir: str, host: str, port: int) -> dict[str, Any]:
    backend = get_backend(backend_name)
    cmd = (
        f"cd {remote_dir!r}; "
        "nohup python3 codex_vm_guest_agent.py "
        f"--host {host!r} --port {port} --helper ./codex-vm-guest-helper "
        "</dev/null >agent.log 2>&1 & printf '%s\\n' $!"
    )
    result = backend.exec(vm, ["sh", "-lc", cmd]).check()
    return {"backend": backend.name, "vm": vm, "pid": result.stdout.strip(), "host": host, "port": port, "log": f"{remote_dir}/agent.log"}


def stop_guest_agent(vm: str, backend_name: str | None) -> dict[str, Any]:
    backend = get_backend(backend_name)
    result = backend.exec(vm, ["sh", "-lc", "pkill -f codex_vm_guest_agent.py || true"]).check()
    return {"backend": backend.name, "vm": vm, "stopped": True, "stdout": result.stdout, "stderr": result.stderr}


def call_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "vm_diagnose":
        return all_diagnostics()
    if name == "vm_list":
        return get_backend(args.get("backend")).list()
    if name == "vm_start":
        return get_backend(args.get("backend")).start(args["vm"], headless=not args.get("visible", False) and not args.get("vnc", False), disposable=args.get("disposable", False), vnc=args.get("vnc", False), mounts=args.get("mounts") or [])
    if name == "vm_stop":
        return get_backend(args.get("backend")).stop(args["vm"])
    if name == "vm_clone":
        return get_backend(args.get("backend")).clone(args["source"], args["name"])
    if name == "vm_prepare_base":
        tart = get_backend("tart")
        return tart.clone_public_base(args.get("name", "codex-tahoe-base"), args.get("image", "ghcr.io/cirruslabs/macos-tahoe-base:latest"))  # type: ignore[attr-defined]
    if name == "vm_delete":
        return get_backend(args.get("backend")).delete(args["vm"])
    if name == "vm_ip":
        return get_backend(args.get("backend")).ip(args["vm"])
    if name == "vm_exec":
        if args.get("argv"):
            argv = [str(part) for part in args["argv"]]
        elif args.get("command"):
            argv = ["zsh", "-lc", str(args["command"])]
        else:
            raise ValueError("vm_exec requires argv or command")
        result = get_backend(args.get("backend")).exec(args["vm"], argv)
        return {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    if name == "vm_push":
        return get_backend(args.get("backend")).push(args["vm"], args["local_path"], args["remote_path"])
    if name == "vm_start_agent":
        return start_guest_agent(args["vm"], args.get("backend"), args.get("remote_dir", "/Users/admin/codex-vm-agent"), args.get("host", "0.0.0.0"), int(args.get("port", 7042)))
    if name == "vm_stop_agent":
        return stop_guest_agent(args["vm"], args.get("backend"))
    if name == "agent_snapshot":
        return AgentClient(args["host"], int(args.get("port", 7042))).snapshot()
    if name == "agent_ax_tree":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_tree(int(args.get("depth", 5)), int(args.get("max_children", 80)))
    if name == "agent_ax_press":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_press(int(args["id"]), int(args.get("depth", 5)), int(args.get("max_children", 80)))
    if name == "agent_ax_click":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_click(int(args["id"]), int(args.get("depth", 5)), int(args.get("max_children", 80)))
    if name == "agent_ax_set_value":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_set_value(int(args["id"]), args["value"], int(args.get("depth", 5)), int(args.get("max_children", 80)))
    if name == "agent_click":
        return AgentClient(args["host"], int(args.get("port", 7042))).click(int(args["x"]), int(args["y"]), args.get("button", "left"))
    if name == "agent_type":
        return AgentClient(args["host"], int(args.get("port", 7042))).type_text(args["text"])
    raise ValueError(f"unknown tool {name}")


def respond(message_id: Any, result: Any = None, error: Exception | None = None) -> None:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": message_id}
    if error:
        payload["error"] = {"code": -32000, "message": str(error)}
    else:
        payload["result"] = result
    print(json.dumps(payload), flush=True)


def serve_stdio() -> None:
    methods: dict[str, Callable[[dict[str, Any]], Any]] = {
        "initialize": lambda params: {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "codex-vm-bridge", "version": "0.1.0"}},
        "tools/list": lambda params: {"tools": tool_schema()},
        "tools/call": lambda params: {"content": [{"type": "text", "text": json.dumps(call_tool(params["name"], params.get("arguments") or {}), indent=2)}]},
    }
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            method = msg.get("method")
            if method == "notifications/initialized":
                continue
            if method not in methods:
                raise ValueError(f"unsupported method {method}")
            respond(msg.get("id"), methods[method](msg.get("params") or {}))
        except Exception as exc:
            respond(None, error=exc)
