#!/usr/bin/env python3
"""odoo_local_server.py - entry point of the `odoo-local` stdio MCP server.

Launch: python3 <plugin>/scripts/mcp/odoo_local_server.py   (speaks MCP on stdin/stdout)

stdout is reserved for protocol messages: before anything else runs, the real stdout is duplicated
into a private stream for the server and fd 1 is re-pointed at stderr, so a stray print() or a
child that inherits fd 1 can never corrupt the wire.

On a Python older than MIN_PYTHON the full server cannot load; a degraded loop still answers
initialize / ping / tools/list and returns every tools/call as the named error PYTHON_TOO_OLD, so
the agent sees an actionable remedy instead of a server that silently failed to start. This file
therefore sticks to syntax very old Python 3 parses (no f-strings, no annotations).
"""

import json
import os
import sys

MIN_PYTHON = (3, 8)

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def _log(msg):
    sys.stderr.write("odoo-local: %s\n" % msg)
    sys.stderr.flush()


def degraded_main(in_stream, out_stream):
    """Minimal MCP loop for an interpreter below MIN_PYTHON. Streams are binary."""
    import odoo_local
    from odoo_local import errors

    try:
        from odoo_local.cli import plugin_version
        version = plugin_version()
    except Exception:
        version = "0.0.0+unknown"
    found = "%d.%d.%d" % tuple(sys.version_info[:3])
    need = "%d.%d" % MIN_PYTHON
    message = "odoo-local needs Python %s or newer; this server was started with Python %s (%s)" % (
        need, found, sys.executable)
    payload = {"error": {"code": "PYTHON_TOO_OLD", "message": message,
                         "remedy": errors.SERVER_CODES["PYTHON_TOO_OLD"],
                         "diagnostics": {"python": found, "executable": sys.executable, "required": need}}}
    text = json.dumps(payload, separators=(",", ":"))

    def send(obj):
        out_stream.write((json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8"))
        out_stream.flush()

    for raw in iter(in_stream.readline, b""):
        try:
            msg = json.loads(raw.decode("utf-8"))
        except ValueError:
            if raw.strip():
                send({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        if not isinstance(msg, dict) or "id" not in msg:
            continue
        rid, method = msg.get("id"), msg.get("method")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": (params.get("protocolVersion")
                                    if params.get("protocolVersion") in odoo_local.SUPPORTED_PROTOCOL_VERSIONS
                                    else odoo_local.SUPPORTED_PROTOCOL_VERSIONS[0]),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "odoo-local", "version": version},
                "instructions": "odoo-local is DISABLED: " + message + ". " + errors.SERVER_CODES["PYTHON_TOO_OLD"],
            }})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": [{
                "name": "server_info",
                "description": "odoo-local is disabled on this Python (PYTHON_TOO_OLD); calling this returns the remedy.",
                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
            }]}})
        elif method == "tools/call":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text", "text": text}], "structuredContent": payload, "isError": True}})
        else:
            send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found: %s" % method}})


def claim_stdout():
    """Take the real stdout for the protocol and re-point fd 1 (and sys.stdout) at stderr.
    Returns the private binary stream the server writes messages to."""
    wire_out = os.fdopen(os.dup(1), "wb")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return wire_out


def main():
    wire_out = claim_stdout()
    in_stream = sys.stdin.buffer

    if sys.version_info[:2] < MIN_PYTHON:
        _log("Python %d.%d is below %d.%d; running in PYTHON_TOO_OLD degraded mode" % (
            sys.version_info[0], sys.version_info[1], MIN_PYTHON[0], MIN_PYTHON[1]))
        degraded_main(in_stream, wire_out)
        return 0

    import logging

    logging.basicConfig(stream=sys.stderr, level=os.environ.get("ODOO_LOCAL_MCP_LOG_LEVEL", "INFO").upper(),
                        format="odoo-local %(levelname)s %(message)s")
    from odoo_local import cli, protocol

    anchor = cli.anchor()
    ctx = protocol.ServerContext(cli.plugin_version(), anchor, cli.PLUGIN_ROOT)
    registry = protocol.build_registry(ctx)
    from odoo_local import tools_lease
    tools_lease.start_heartbeat()  # daemon thread: refreshes this session's leases every 10 min
    from odoo_local import jobs
    jobs.prune_finished()  # opportunistic: finished job records past the build-log retention bound
    logging.getLogger("odoo-local").info(
        "starting v%s pid=%d anchor=%s tools=%s", ctx.version, os.getpid(), anchor.as_dict(), registry.names())
    protocol.Server(registry, ctx, wire_out).serve(in_stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
