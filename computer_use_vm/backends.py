from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import tarfile
from dataclasses import dataclass
from typing import Any


class BridgeError(RuntimeError):
    pass


@dataclass
class CommandResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    def check(self) -> "CommandResult":
        if self.returncode != 0:
            raise BridgeError(
                f"command failed ({self.returncode}): {' '.join(self.argv)}\n"
                f"stdout:\n{self.stdout}\n\nstderr:\n{self.stderr}"
            )
        return self


def run(argv: list[str], *, input_text: str | bytes | None = None, timeout: int = 120) -> CommandResult:
    text_mode = not isinstance(input_text, bytes)
    proc = subprocess.run(
        argv,
        input=input_text,
        text=text_mode,
        capture_output=True,
        timeout=timeout,
    )
    stdout = proc.stdout if isinstance(proc.stdout, str) else proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr if isinstance(proc.stderr, str) else proc.stderr.decode("utf-8", "replace")
    return CommandResult(argv, proc.returncode, stdout, stderr)


def which(name: str) -> str | None:
    return shutil.which(name)


class Backend:
    name = "base"

    def available(self) -> bool:
        raise NotImplementedError

    def diagnose(self) -> dict[str, Any]:
        raise NotImplementedError

    def list(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    def start(
        self,
        vm: str,
        *,
        headless: bool = True,
        disposable: bool = False,
        vnc: bool = False,
        mounts: list[str] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def stop(self, vm: str) -> dict[str, Any]:
        raise NotImplementedError

    def clone(self, source: str, name: str) -> dict[str, Any]:
        raise NotImplementedError

    def delete(self, vm: str) -> dict[str, Any]:
        raise NotImplementedError

    def ip(self, vm: str) -> list[str]:
        raise NotImplementedError

    def exec(self, vm: str, cmd: list[str], *, input_text: str | bytes | None = None) -> CommandResult:
        raise NotImplementedError

    def push(self, vm: str, local_path: str, remote_path: str) -> dict[str, Any]:
        raise NotImplementedError


class TartBackend(Backend):
    name = "tart"

    def __init__(self) -> None:
        self.bin = which("tart")

    def available(self) -> bool:
        return self.bin is not None

    def _run(self, args: list[str], **kwargs: Any) -> CommandResult:
        if not self.bin:
            raise BridgeError("tart is not installed")
        return run([self.bin, *args], **kwargs)

    def diagnose(self) -> dict[str, Any]:
        info: dict[str, Any] = {"backend": self.name, "binary": self.bin, "available": self.available()}
        if self.bin:
            res = self._run(["--version"], timeout=30)
            info["version_stdout"] = res.stdout.strip()
            info["version_stderr"] = res.stderr.strip()
            info["version_ok"] = res.returncode == 0
        return info

    def list(self) -> list[dict[str, Any]]:
        res = self._run(["list", "--format", "json"]).check()
        data = json.loads(res.stdout or "[]")
        if isinstance(data, list):
            return data
        return []

    def start(
        self,
        vm: str,
        *,
        headless: bool = True,
        disposable: bool = False,
        vnc: bool = False,
        mounts: list[str] | None = None,
    ) -> dict[str, Any]:
        args = ["run"]
        if vnc:
            args.append("--vnc")
        elif headless:
            args.append("--no-graphics")
        for mount in mounts or []:
            args.extend(["--dir", mount])
        if disposable:
            # Tart's disposable behavior is modeled by clone/delete; keep this explicit.
            pass
        args.append(vm)
        if not self.bin:
            raise BridgeError("tart is not installed")
        log_path = os.path.join(tempfile.gettempdir(), f"computer-use-vm-tart-{re.sub(r'[^A-Za-z0-9_.-]', '_', vm)}.log")
        log = open(log_path, "ab")
        proc = subprocess.Popen([self.bin, *args], stdout=log, stderr=log, stdin=subprocess.DEVNULL, start_new_session=True)
        return {"backend": self.name, "vm": vm, "started": True, "headless": headless, "vnc": vnc, "mounts": mounts or [], "pid": proc.pid, "log": log_path}

    def stop(self, vm: str) -> dict[str, Any]:
        res = self._run(["stop", vm]).check()
        return {"backend": self.name, "vm": vm, "stopped": True, "stdout": res.stdout}

    def clone(self, source: str, name: str) -> dict[str, Any]:
        res = self._run(["clone", source, name]).check()
        return {"backend": self.name, "source": source, "name": name, "stdout": res.stdout}

    def clone_public_base(self, name: str, image: str = "ghcr.io/cirruslabs/macos-tahoe-base:latest") -> dict[str, Any]:
        res = self._run(["clone", image, name], timeout=7200).check()
        return {"backend": self.name, "image": image, "name": name, "stdout": res.stdout}

    def delete(self, vm: str) -> dict[str, Any]:
        res = self._run(["delete", vm]).check()
        return {"backend": self.name, "vm": vm, "deleted": True, "stdout": res.stdout}

    def ip(self, vm: str) -> list[str]:
        res = self._run(["ip", vm]).check()
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    def exec(self, vm: str, cmd: list[str], *, input_text: str | bytes | None = None) -> CommandResult:
        if not self.bin:
            raise BridgeError("tart is not installed")
        args = ["exec"]
        if input_text is not None:
            args.append("-i")
        return run([self.bin, *args, vm, *cmd], input_text=input_text)

    def push(self, vm: str, local_path: str, remote_path: str) -> dict[str, Any]:
        local_path = os.path.abspath(os.path.expanduser(local_path))
        if not os.path.exists(local_path):
            raise BridgeError(f"local path does not exist: {local_path}")
        remote_parent = os.path.dirname(remote_path.rstrip("/")) or "."
        remote_name = os.path.basename(remote_path.rstrip("/"))
        if not remote_name:
            raise BridgeError("remote path must name a file or directory")
        with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
            with tarfile.open(archive.name, "w") as tar:
                tar.add(local_path, arcname=remote_name)
            archive.seek(0)
            data = archive.read()
        quoted_parent = remote_parent.replace("'", "'\\''")
        res = self.exec(vm, ["sh", "-lc", f"mkdir -p '{quoted_parent}' && tar -xf - -C '{quoted_parent}'"], input_text=data).check()
        return {"backend": self.name, "vm": vm, "local": local_path, "remote": remote_path, "stdout": res.stdout}


class UTMBackend(Backend):
    name = "utm"

    def __init__(self) -> None:
        self.bin = which("utmctl")

    def available(self) -> bool:
        return self.bin is not None

    def _run(self, args: list[str], **kwargs: Any) -> CommandResult:
        if not self.bin:
            raise BridgeError("utmctl is not installed")
        return run([self.bin, *args], **kwargs)

    def diagnose(self) -> dict[str, Any]:
        info: dict[str, Any] = {"backend": self.name, "binary": self.bin, "available": self.available()}
        if self.bin:
            res = self._run(["version"], timeout=30)
            info["version_stdout"] = res.stdout.strip()
            info["version_stderr"] = res.stderr.strip()
            info["version_ok"] = res.returncode == 0
            if "errAEEventNotPermitted" in res.stderr or "OSStatus error -1743" in res.stderr:
                info["permission_hint"] = "Grant Automation permission for the terminal app to control UTM, and run from a logged-in GUI session."
        return info

    def list(self) -> list[dict[str, Any]]:
        res = self._run(["list"]).check()
        rows = []
        for line in res.stdout.splitlines()[1:]:
            match = re.match(r"(?P<uuid>\S+)\s+(?P<status>\S+)\s+(?P<name>.+)", line)
            if match:
                rows.append(match.groupdict())
        return rows

    def start(
        self,
        vm: str,
        *,
        headless: bool = True,
        disposable: bool = False,
        vnc: bool = False,
        mounts: list[str] | None = None,
    ) -> dict[str, Any]:
        if mounts:
            raise BridgeError("directory mounts are only supported by the Tart backend; use push for UTM")
        args = ["start"]
        if headless:
            args.append("--hide")
        if disposable:
            args.append("--disposable")
        args.append(vm)
        res = self._run(args).check()
        return {"backend": self.name, "vm": vm, "started": True, "headless": headless, "disposable": disposable, "stdout": res.stdout}

    def stop(self, vm: str) -> dict[str, Any]:
        res = self._run(["stop", vm]).check()
        return {"backend": self.name, "vm": vm, "stopped": True, "stdout": res.stdout}

    def clone(self, source: str, name: str) -> dict[str, Any]:
        res = self._run(["clone", source, "--name", name]).check()
        return {"backend": self.name, "source": source, "name": name, "stdout": res.stdout}

    def delete(self, vm: str) -> dict[str, Any]:
        res = self._run(["delete", vm]).check()
        return {"backend": self.name, "vm": vm, "deleted": True, "stdout": res.stdout}

    def ip(self, vm: str) -> list[str]:
        res = self._run(["ip-address", vm]).check()
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]

    def exec(self, vm: str, cmd: list[str], *, input_text: str | bytes | None = None) -> CommandResult:
        return self._run(["exec", vm, "--cmd", *cmd], input_text=input_text)

    def push(self, vm: str, local_path: str, remote_path: str) -> dict[str, Any]:
        with open(local_path, "rb") as handle:
            data = handle.read()
        res = self._run(["file", "push", vm, remote_path], input_text=data).check()
        return {"backend": self.name, "vm": vm, "local": local_path, "remote": remote_path, "stdout": res.stdout}


def get_backend(name: str | None = None) -> Backend:
    backends: dict[str, Backend] = {"tart": TartBackend(), "utm": UTMBackend()}
    if name:
        if name not in backends:
            raise BridgeError(f"unknown backend {name!r}; expected one of: {', '.join(backends)}")
        return backends[name]
    for candidate in (backends["tart"], backends["utm"]):
        if candidate.available():
            return candidate
    raise BridgeError("no supported VM backend found; install Tart or UTM")


def all_diagnostics() -> dict[str, Any]:
    return {
        "host": {
            "cwd": os.getcwd(),
            "python": shutil.which("python3"),
            "ssh": shutil.which("ssh"),
            "scp": shutil.which("scp"),
        },
        "backends": [TartBackend().diagnose(), UTMBackend().diagnose()],
    }
