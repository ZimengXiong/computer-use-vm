from __future__ import annotations

import json
import sys
from typing import Any, Callable

from .agent_client import AgentClient
from .backends import all_diagnostics, get_backend

LAUNCH_AGENT_LABEL_PREFIX = "local.computer-use.vm-agent"
LEGACY_LAUNCH_AGENT_LABELS = ["local.codex.vm-agent"]


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


def tool_schema() -> list[dict[str, Any]]:
    return [
        {"name": "vm_diagnose", "description": "Report local VM bridge backend availability and permission diagnostics.", "inputSchema": {"type": "object", "properties": {}}},
        {"name": "vm_list", "description": "List VMs from Tart or UTM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}}}},
        {"name": "vm_start", "description": "Start a VM in headless/hidden mode by default, or VNC/visible mode for screen introspection. Tart supports directory shares through mounts, passed directly to tart run --dir.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "visible": {"type": "boolean"}, "vnc": {"type": "boolean"}, "disposable": {"type": "boolean"}, "mounts": {"type": "array", "items": {"type": "string"}}}, "required": ["vm"]}},
        {"name": "vm_stop", "description": "Stop a VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_clone", "description": "Clone a source VM to a named working VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "source": {"type": "string"}, "name": {"type": "string"}}, "required": ["source", "name"]}},
        {"name": "vm_prepare_base", "description": "Clone the public Cirrus macOS Tahoe Tart base image into a local base VM.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string", "default": "computer-use-tahoe-base"}, "image": {"type": "string", "default": "ghcr.io/cirruslabs/macos-tahoe-base:latest"}}}},
        {"name": "vm_delete", "description": "Delete a VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_ip", "description": "Return known IP addresses for a VM.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_exec", "description": "Run a terminal command inside a VM. Pass argv for direct execution, or command for a shell command run via zsh -lc.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "argv": {"type": "array", "items": {"type": "string"}}, "command": {"type": "string"}}, "required": ["vm"]}},
        {"name": "vm_push", "description": "Copy a host file or directory into a VM. Prefer Tart mounts on vm_start for large workspaces.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "local_path": {"type": "string"}, "remote_path": {"type": "string"}}, "required": ["vm", "local_path", "remote_path"]}},
        {"name": "vm_start_agent", "description": "Start the installed in-guest HTTP computer-use agent.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}, "remote_dir": {"type": "string", "default": "/Users/admin/computer-use-vm-agent"}, "host": {"type": "string", "default": "0.0.0.0"}, "port": {"type": "integer", "default": 7042}}, "required": ["vm"]}},
        {"name": "vm_stop_agent", "description": "Stop the installed in-guest HTTP computer-use agent.", "inputSchema": {"type": "object", "properties": {"backend": {"type": "string", "enum": ["tart", "utm"]}, "vm": {"type": "string"}}, "required": ["vm"]}},
        {"name": "agent_permissions", "description": "Return guest Screen Recording and Accessibility permission status for the in-guest helper.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}}, "required": ["host"]}},
        {"name": "agent_snapshot", "description": "Return guest screen metadata and screenshot base64 from the in-guest agent. If app is set, return app-scoped state.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}}, "required": ["host"]}},
        {"name": "agent_list_apps", "description": "List running guest apps with names, bundle identifiers, and PIDs.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}}, "required": ["host"]}},
        {"name": "agent_activate_app", "description": "Activate a guest app by localized name or bundle identifier.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}}, "required": ["host", "app"]}},
        {"name": "agent_state", "description": "Return screenshot and app/window accessibility tree, optionally scoped to an app name or bundle identifier.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host"]}},
        {"name": "agent_ax_tree", "description": "Return the guest app/window accessibility tree with element roles, labels, bounds, and actions.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host"]}},
        {"name": "agent_ax_press", "description": "Perform AXPress on an element id from the latest equivalent AX tree traversal.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "id": {"type": "integer"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "id"]}},
        {"name": "agent_ax_click", "description": "Click the center of an element id from the latest equivalent AX tree traversal.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "id": {"type": "integer"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "id"]}},
        {"name": "agent_ax_set_value", "description": "Set an accessibility element value by id, falling back to focus and paste.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "id": {"type": "integer"}, "value": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "id", "value"]}},
        {"name": "agent_ax_action", "description": "Invoke a named accessibility action exposed by an element.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "id": {"type": "integer"}, "action": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "id", "action"]}},
        {"name": "agent_click", "description": "Click guest screen coordinates through the in-guest agent.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "default": "left"}, "click_count": {"type": "integer", "default": 1}}, "required": ["host", "x", "y"]}},
        {"name": "agent_drag", "description": "Drag from one guest screen coordinate to another.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "from_x": {"type": "integer"}, "from_y": {"type": "integer"}, "to_x": {"type": "integer"}, "to_y": {"type": "integer"}}, "required": ["host", "from_x", "from_y", "to_x", "to_y"]}},
        {"name": "agent_scroll", "description": "Scroll the guest, optionally after focusing an accessibility element id.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "id": {"type": "integer"}, "direction": {"type": "string", "enum": ["up", "down", "left", "right"]}, "pages": {"type": "number", "default": 1}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "direction"]}},
        {"name": "agent_type", "description": "Type text in the guest through the in-guest agent.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "text": {"type": "string"}}, "required": ["host", "text"]}},
        {"name": "agent_key", "description": "Press a key or key combination in the guest through the in-guest agent.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "key": {"type": "string"}, "modifiers": {"type": "array", "items": {"type": "string"}}}, "required": ["host", "key"]}},
        {"name": "get_app_state", "description": "Native Computer Use compatible alias: get screenshot and AX tree for a guest app.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "app"]}},
        {"name": "list_apps", "description": "Native Computer Use compatible alias: list running guest apps.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}}, "required": ["host"]}},
        {"name": "click", "description": "Native Computer Use compatible alias: click an element index or coordinates in a guest app.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "element_index": {"type": "string"}, "x": {"type": "number"}, "y": {"type": "number"}, "mouse_button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"}, "click_count": {"type": "integer", "default": 1}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "app"]}},
        {"name": "type_text", "description": "Native Computer Use compatible alias: type literal text in the guest.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "text": {"type": "string"}}, "required": ["host", "app", "text"]}},
        {"name": "set_value", "description": "Native Computer Use compatible alias: set an accessibility element value.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "element_index": {"type": "string"}, "value": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "app", "element_index", "value"]}},
        {"name": "perform_secondary_action", "description": "Native Computer Use compatible alias: invoke a named accessibility action on an element.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "element_index": {"type": "string"}, "action": {"type": "string"}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "app", "element_index", "action"]}},
        {"name": "drag", "description": "Native Computer Use compatible alias: drag in guest screen coordinates.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "from_x": {"type": "number"}, "from_y": {"type": "number"}, "to_x": {"type": "number"}, "to_y": {"type": "number"}}, "required": ["host", "app", "from_x", "from_y", "to_x", "to_y"]}},
        {"name": "scroll", "description": "Native Computer Use compatible alias: scroll an element in a direction by pages.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "element_index": {"type": "string"}, "direction": {"type": "string", "enum": ["up", "down", "left", "right"]}, "pages": {"type": "number", "default": 1}, "depth": {"type": "integer", "default": 5}, "max_children": {"type": "integer", "default": 80}}, "required": ["host", "app", "element_index", "direction"]}},
        {"name": "press_key", "description": "Native Computer Use compatible alias: press a key or key combination in the guest.", "inputSchema": {"type": "object", "properties": {"host": {"type": "string"}, "port": {"type": "integer", "default": 7042}, "app": {"type": "string"}, "key": {"type": "string"}}, "required": ["host", "app", "key"]}},
    ]


def start_guest_agent(vm: str, backend_name: str | None, remote_dir: str, host: str, port: int) -> dict[str, Any]:
    backend = get_backend(backend_name)
    label = launch_agent_label(port)
    path = launch_agent_path(port)
    plist = launch_agent_plist(remote_dir, port).replace("'", "'\\''")
    labels = " ".join([label, *LEGACY_LAUNCH_AGENT_LABELS])
    cmd = (
        "uid=$(id -u); "
        "mkdir -p /Users/admin/Library/LaunchAgents; "
        f"printf '%s' '{plist}' > {path!r}; "
        f"chmod 644 {path!r}; "
        f"for label in {labels}; do launchctl bootout gui/$uid/$label >/dev/null 2>&1 || true; done; "
        f"pids=$(lsof -tiTCP:{port} -sTCP:LISTEN 2>/dev/null || true); [ -n \"$pids\" ] && kill $pids >/dev/null 2>&1 || true; "
        f"launchctl bootstrap gui/$uid {path!r} >/dev/null 2>&1 || true; "
        f"launchctl kickstart -k gui/$uid/{label}"
    )
    result = backend.exec(vm, ["sh", "-lc", cmd]).check()
    return {"backend": backend.name, "vm": vm, "started": True, "host": host, "port": port, "log": f"{remote_dir}/agent.log", "launch_agent": label, "stdout": result.stdout, "stderr": result.stderr}


def stop_guest_agent(vm: str, backend_name: str | None) -> dict[str, Any]:
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


def element_id(value: Any) -> int:
    return int(str(value))


def parse_key_combo(value: str) -> tuple[str, list[str]]:
    parts = [part for part in value.replace("super", "command").split("+") if part]
    if not parts:
        raise ValueError("key is required")
    modifiers = [part for part in parts[:-1]]
    return parts[-1], modifiers


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
        return tart.clone_public_base(args.get("name", "computer-use-tahoe-base"), args.get("image", "ghcr.io/cirruslabs/macos-tahoe-base:latest"))  # type: ignore[attr-defined]
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
        return start_guest_agent(args["vm"], args.get("backend"), args.get("remote_dir", "/Users/admin/computer-use-vm-agent"), args.get("host", "0.0.0.0"), int(args.get("port", 7042)))
    if name == "vm_stop_agent":
        return stop_guest_agent(args["vm"], args.get("backend"))
    if name == "agent_snapshot":
        return AgentClient(args["host"], int(args.get("port", 7042))).snapshot(args.get("app"))
    if name == "agent_permissions":
        return AgentClient(args["host"], int(args.get("port", 7042))).permissions()
    if name == "agent_list_apps":
        return AgentClient(args["host"], int(args.get("port", 7042))).list_apps()
    if name == "agent_activate_app":
        return AgentClient(args["host"], int(args.get("port", 7042))).activate_app(args["app"])
    if name == "agent_state":
        return AgentClient(args["host"], int(args.get("port", 7042))).state(int(args.get("depth", 5)), int(args.get("max_children", 80)), args.get("app"))
    if name == "agent_ax_tree":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_tree(int(args.get("depth", 5)), int(args.get("max_children", 80)), args.get("app"))
    if name == "agent_ax_press":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_press(int(args["id"]), int(args.get("depth", 5)), int(args.get("max_children", 80)), args.get("app"))
    if name == "agent_ax_click":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_click(int(args["id"]), int(args.get("depth", 5)), int(args.get("max_children", 80)), args.get("app"))
    if name == "agent_ax_set_value":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_set_value(int(args["id"]), args["value"], int(args.get("depth", 5)), int(args.get("max_children", 80)), args.get("app"))
    if name == "agent_ax_action":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_action(int(args["id"]), args["action"], int(args.get("depth", 5)), int(args.get("max_children", 80)), args.get("app"))
    if name == "agent_click":
        return AgentClient(args["host"], int(args.get("port", 7042))).click(int(args["x"]), int(args["y"]), args.get("button", "left"), int(args.get("click_count", 1)))
    if name == "agent_drag":
        return AgentClient(args["host"], int(args.get("port", 7042))).drag(int(args["from_x"]), int(args["from_y"]), int(args["to_x"]), int(args["to_y"]))
    if name == "agent_scroll":
        return AgentClient(args["host"], int(args.get("port", 7042))).scroll(args["direction"], float(args.get("pages", 1)), args.get("id"), int(args.get("depth", 5)), int(args.get("max_children", 80)), args.get("app"))
    if name == "agent_type":
        return AgentClient(args["host"], int(args.get("port", 7042))).type_text(args["text"])
    if name == "agent_key":
        return AgentClient(args["host"], int(args.get("port", 7042))).key(args["key"], args.get("modifiers") or [])
    if name == "get_app_state":
        return AgentClient(args["host"], int(args.get("port", 7042))).state(int(args.get("depth", 5)), int(args.get("max_children", 80)), args["app"])
    if name == "list_apps":
        return AgentClient(args["host"], int(args.get("port", 7042))).list_apps()
    if name == "click":
        client = AgentClient(args["host"], int(args.get("port", 7042)))
        if args.get("element_index") is not None:
            return client.ax_click(element_id(args["element_index"]), int(args.get("depth", 5)), int(args.get("max_children", 80)), args["app"])
        if args.get("x") is None or args.get("y") is None:
            raise ValueError("click requires element_index or x/y")
        return client.click(int(args["x"]), int(args["y"]), args.get("mouse_button", "left"), int(args.get("click_count", 1)))
    if name == "type_text":
        return AgentClient(args["host"], int(args.get("port", 7042))).type_text(args["text"])
    if name == "set_value":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_set_value(element_id(args["element_index"]), args["value"], int(args.get("depth", 5)), int(args.get("max_children", 80)), args["app"])
    if name == "perform_secondary_action":
        return AgentClient(args["host"], int(args.get("port", 7042))).ax_action(element_id(args["element_index"]), args["action"], int(args.get("depth", 5)), int(args.get("max_children", 80)), args["app"])
    if name == "drag":
        return AgentClient(args["host"], int(args.get("port", 7042))).drag(int(args["from_x"]), int(args["from_y"]), int(args["to_x"]), int(args["to_y"]))
    if name == "scroll":
        return AgentClient(args["host"], int(args.get("port", 7042))).scroll(args["direction"], float(args.get("pages", 1)), element_id(args["element_index"]), int(args.get("depth", 5)), int(args.get("max_children", 80)), args["app"])
    if name == "press_key":
        key, modifiers = parse_key_combo(args["key"])
        return AgentClient(args["host"], int(args.get("port", 7042))).key(key, modifiers)
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
        "initialize": lambda params: {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "computer-use-vm", "version": "0.1.4"}},
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
