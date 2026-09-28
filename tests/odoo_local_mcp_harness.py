"""Shared harness for the odoo-local MCP server tests (not a test module itself).

Spawns the REAL server entry point as a subprocess and talks newline-delimited JSON-RPC to it over
pipes, exactly as Claude Code does. Every stdout line the server writes is checked to be a JSON-RPC
2.0 message - a stray print on stdout fails the test that caused it.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "odoo-ai-agents"
MCP_DIR = PLUGIN / "scripts" / "mcp"
SERVER = MCP_DIR / "odoo_local_server.py"
PACKAGE = MCP_DIR / "odoo_local"
LIB_DIR = PLUGIN / "scripts" / "lib"

_SCRUB = ("ODOO_AI_INSTANCES", "ODOO_AI_PROJECT_DIR", "ODOO_AI_WORKTREE_DIR", "ODOO_AI_SESSION_ANCHOR", "ODOO_AI_VIA")


def import_package():
    """Import the odoo_local package in-process (for unit-level tests)."""
    if str(MCP_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_DIR))
    import odoo_local  # noqa: F401
    from odoo_local import cli, errors, jobs, protocol, tools_catalog  # noqa: F401

    return sys.modules["odoo_local"]


def hermetic_env(home: Path, **extra) -> dict:
    """The ambient env with every odoo-ai override scrubbed and ODOO_AI_HOME pinned to `home`."""
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    env["ODOO_AI_HOME"] = str(home)
    env.update({k: str(v) for k, v in extra.items()})
    return env


class McpClient:
    def __init__(self, env: dict, cwd: Path, timeout: float = 30.0):
        self.timeout = timeout
        self.proc = subprocess.Popen(
            [sys.executable, str(SERVER)],
            cwd=str(cwd),
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._next_id = 0
        self._lines: "queue.Queue[dict]" = queue.Queue()
        self.stdout_violations: list = []
        self.stderr_chunks: list = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self):
        for raw in iter(self.proc.stdout.readline, b""):
            try:
                msg = json.loads(raw.decode("utf-8"))
            except ValueError:
                self.stdout_violations.append(raw)
                continue
            if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
                self.stdout_violations.append(raw)
                continue
            self._lines.put(msg)

    def _read_stderr(self):
        for raw in iter(self.proc.stderr.readline, b""):
            self.stderr_chunks.append(raw.decode("utf-8", "replace"))

    @property
    def stderr(self) -> str:
        return "".join(self.stderr_chunks)

    # -- sending -----------------------------------------------------------
    def send_raw(self, line: str):
        self.proc.stdin.write(line.encode("utf-8") + b"\n")
        self.proc.stdin.flush()

    def send(self, obj):
        self.send_raw(json.dumps(obj))

    def notify(self, method: str, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)

    def request_async(self, method: str, params=None):
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": self._next_id, "method": method}
        if params is not None:
            msg["params"] = params
        self.send(msg)
        return self._next_id

    # -- receiving ---------------------------------------------------------
    def next_message(self, timeout=None) -> dict:
        return self._lines.get(timeout=timeout or self.timeout)

    def wait_for(self, req_id, timeout=None) -> dict:
        pending = []
        try:
            while True:
                msg = self.next_message(timeout)
                if msg.get("id") == req_id:
                    return msg
                pending.append(msg)
        finally:
            for m in pending:
                self._lines.put(m)

    def request(self, method: str, params=None, timeout=None) -> dict:
        return self.wait_for(self.request_async(method, params), timeout)

    def initialize(self, version="2025-06-18") -> dict:
        resp = self.request("initialize", {"protocolVersion": version, "capabilities": {},
                                           "clientInfo": {"name": "pytest", "version": "0"}})
        self.notify("notifications/initialized")
        return resp

    def call(self, name: str, arguments=None, timeout=None) -> dict:
        """tools/call -> the CallToolResult dict (asserts it is a result, not a protocol error)."""
        params = {"name": name}
        if arguments is not None:
            params["arguments"] = arguments
        resp = self.request("tools/call", params, timeout)
        assert "result" in resp, resp
        return resp["result"]

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        assert not self.stdout_violations, "non-JSON-RPC bytes on stdout: %r" % self.stdout_violations

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def structured(result: dict) -> dict:
    """structuredContent, after checking the text block mirrors it (the compact-JSON contract)."""
    sc = result["structuredContent"]
    assert result["content"][0]["type"] == "text"
    assert json.loads(result["content"][0]["text"]) == sc
    return sc
