#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class AgentState:
    def __init__(self, helper: str) -> None:
        self.helper = helper

    def run_helper(self, *args: str) -> dict[str, Any]:
        proc = subprocess.run([self.helper, *args], text=True, capture_output=True, timeout=30)
        payload = proc.stdout.strip() or proc.stderr.strip() or "{}"
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = {"raw": payload}
        if proc.returncode != 0:
            raise RuntimeError(data.get("error") or payload or f"helper exited {proc.returncode}")
        return data


def make_handler(state: AgentState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ComputerUseVMGuestAgent/0.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length == 0:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def send_json(self, data: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def route(self) -> dict[str, Any]:
            if self.path == "/ping":
                return {"ok": True, "agent": "computer-use-vm-guest-agent"}
            if self.path == "/permissions":
                return state.run_helper("permissions")
            if self.path == "/list-apps":
                return state.run_helper("list-apps")
            if self.path == "/activate-app":
                body = self.read_json()
                return state.run_helper("activate-app", body["app"])
            if self.path == "/screenshot":
                return state.run_helper("screenshot")
            if self.path == "/state":
                body = self.read_json()
                args = [str(body.get("depth", 5)), str(body.get("max_children", 80))]
                if body.get("app"):
                    args.append(body["app"])
                return state.run_helper("state", *args)
            if self.path.startswith("/ax-tree"):
                body = self.read_json()
                args = [str(body.get("depth", 5)), str(body.get("max_children", 80))]
                if body.get("app"):
                    args.append(body["app"])
                return state.run_helper("ax-tree", *args)
            if self.path == "/ax-press":
                body = self.read_json()
                args = [str(body["id"]), str(body.get("depth", 5)), str(body.get("max_children", 80))]
                if body.get("app"):
                    args.append(body["app"])
                return state.run_helper("ax-press", *args)
            if self.path == "/ax-click":
                body = self.read_json()
                args = [str(body["id"]), str(body.get("depth", 5)), str(body.get("max_children", 80))]
                if body.get("app"):
                    args.append(body["app"])
                return state.run_helper("ax-click", *args)
            if self.path == "/ax-set-value":
                body = self.read_json()
                args = [str(body["id"]), body["value"], str(body.get("depth", 5)), str(body.get("max_children", 80))]
                if body.get("app"):
                    args.append(body["app"])
                return state.run_helper("ax-set-value", *args)
            if self.path == "/ax-action":
                body = self.read_json()
                args = [str(body["id"]), body["action"], str(body.get("depth", 5)), str(body.get("max_children", 80))]
                if body.get("app"):
                    args.append(body["app"])
                return state.run_helper("ax-action", *args)
            if self.path == "/snapshot":
                shot = state.run_helper("screenshot")
                perms = state.run_helper("permissions")
                ax_tree = state.run_helper("ax-tree", "5", "80")
                return {**shot, "permissions": perms, "ax_tree": ax_tree}
            if self.path == "/click":
                body = self.read_json()
                return state.run_helper("click", str(body["x"]), str(body["y"]), body.get("button", "left"), str(body.get("click_count", 1)))
            if self.path == "/drag":
                body = self.read_json()
                return state.run_helper("drag", str(body["from_x"]), str(body["from_y"]), str(body["to_x"]), str(body["to_y"]))
            if self.path == "/scroll":
                body = self.read_json()
                if body.get("id") is not None:
                    args = [str(body["id"]), str(body.get("depth", 5)), str(body.get("max_children", 80))]
                    if body.get("app"):
                        args.append(body["app"])
                    state.run_helper("ax-click", *args)
                return state.run_helper("scroll", body["direction"], str(body.get("pages", 1)))
            if self.path == "/type":
                body = self.read_json()
                return state.run_helper("type", body["text"])
            if self.path == "/key":
                body = self.read_json()
                return state.run_helper("key", body["key"], *body.get("modifiers", []))
            raise KeyError(self.path)

        def do_GET(self) -> None:
            try:
                self.send_json(self.route())
            except KeyError:
                self.send_json({"error": "not found", "path": self.path}, 404)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)

        def do_POST(self) -> None:
            self.do_GET()

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7042)
    parser.add_argument("--helper", default="./computer-use-vm-guest-helper")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), make_handler(AgentState(args.helper)))
    print(json.dumps({"ok": True, "host": args.host, "port": args.port}), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
