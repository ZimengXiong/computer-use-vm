from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from typing import Any


class AgentClient:
    def __init__(self, host: str, port: int = 7042, timeout: int = 30) -> None:
        self.base = f"http://{host}:{port}"
        self.timeout = timeout

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{self.base}{path}", data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"agent request failed: HTTP {exc.code}: {detail}") from exc
        return json.loads(body or "{}")

    def ping(self) -> dict[str, Any]:
        return self._request("/ping")

    def permissions(self) -> dict[str, Any]:
        return self._request("/permissions")

    def list_apps(self) -> dict[str, Any]:
        return self._request("/list-apps")

    def activate_app(self, app: str) -> dict[str, Any]:
        return self._request("/activate-app", {"app": app})

    def snapshot(self, app: str | None = None) -> dict[str, Any]:
        return self._request("/snapshot" if app is None else "/state", {"app": app} if app else None)

    def state(self, depth: int = 5, max_children: int = 80, app: str | None = None) -> dict[str, Any]:
        return self._request("/state", {"depth": depth, "max_children": max_children, "app": app})

    def ax_tree(self, depth: int = 5, max_children: int = 80, app: str | None = None) -> dict[str, Any]:
        return self._request("/ax-tree", {"depth": depth, "max_children": max_children, "app": app})

    def ax_press(self, element_id: int, depth: int = 5, max_children: int = 80, app: str | None = None) -> dict[str, Any]:
        return self._request("/ax-press", {"id": element_id, "depth": depth, "max_children": max_children, "app": app})

    def ax_click(self, element_id: int, depth: int = 5, max_children: int = 80, app: str | None = None) -> dict[str, Any]:
        return self._request("/ax-click", {"id": element_id, "depth": depth, "max_children": max_children, "app": app})

    def ax_set_value(self, element_id: int, value: str, depth: int = 5, max_children: int = 80, app: str | None = None) -> dict[str, Any]:
        return self._request("/ax-set-value", {"id": element_id, "value": value, "depth": depth, "max_children": max_children, "app": app})

    def ax_action(self, element_id: int, action: str, depth: int = 5, max_children: int = 80, app: str | None = None) -> dict[str, Any]:
        return self._request("/ax-action", {"id": element_id, "action": action, "depth": depth, "max_children": max_children, "app": app})

    def screenshot(self, output: str | None = None) -> dict[str, Any]:
        result = self._request("/screenshot")
        if output:
            with open(output, "wb") as handle:
                handle.write(base64.b64decode(result["png_base64"]))
            result = {k: v for k, v in result.items() if k != "png_base64"}
            result["output"] = output
        return result

    def click(self, x: int, y: int, button: str = "left", click_count: int = 1) -> dict[str, Any]:
        return self._request("/click", {"x": x, "y": y, "button": button, "click_count": click_count})

    def drag(self, from_x: int, from_y: int, to_x: int, to_y: int) -> dict[str, Any]:
        return self._request("/drag", {"from_x": from_x, "from_y": from_y, "to_x": to_x, "to_y": to_y})

    def scroll(self, direction: str, pages: float = 1, element_id: int | None = None, depth: int = 5, max_children: int = 80, app: str | None = None) -> dict[str, Any]:
        return self._request("/scroll", {"direction": direction, "pages": pages, "id": element_id, "depth": depth, "max_children": max_children, "app": app})

    def type_text(self, text: str) -> dict[str, Any]:
        return self._request("/type", {"text": text})

    def key(self, key: str, modifiers: list[str] | None = None) -> dict[str, Any]:
        return self._request("/key", {"key": key, "modifiers": modifiers or []})
