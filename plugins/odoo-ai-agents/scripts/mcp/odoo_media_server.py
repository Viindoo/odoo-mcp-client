#!/usr/bin/env python3
"""odoo_media_server.py - entry point of the `odoo-media` stdio MCP server (narration speech and
YouTube publishing: the tools that need a value the operator configured through the plugin's
options). Launch: python3 <plugin>/scripts/mcp/odoo_media_server.py

Shares the protocol frame, the error table and the degraded PYTHON_TOO_OLD loop with odoo-local
(scripts/mcp/odoo_local_server.py); the values reach this process as environment variables the
plugin's .mcp.json maps from `${user_config.*}`. Syntax stays parseable by very old Python 3.
"""

import os
import sys

MIN_PYTHON = (3, 8)
SERVER_NAME = "odoo-media"

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


def main():
    import odoo_local_server
    wire_out = odoo_local_server.claim_stdout()
    in_stream = sys.stdin.buffer
    if sys.version_info[:2] < MIN_PYTHON:
        sys.stderr.write("%s: Python %d.%d is below %d.%d; running in PYTHON_TOO_OLD degraded mode\n" % (
            SERVER_NAME, sys.version_info[0], sys.version_info[1], MIN_PYTHON[0], MIN_PYTHON[1]))
        odoo_local_server.stabilize_cwd()
        odoo_local_server.degraded_main(in_stream, wire_out, server_name=SERVER_NAME)
        return 0
    odoo_local_server.stabilize_cwd(odoo_local_server._state_root_or_none())

    import logging

    logging.basicConfig(stream=sys.stderr, level=os.environ.get("ODOO_MEDIA_MCP_LOG_LEVEL", "INFO").upper(),
                        format="odoo-media %(levelname)s %(message)s")
    from odoo_local import cli, protocol
    from odoo_media import registry as media_registry

    ctx = protocol.ServerContext(cli.plugin_version(), cli.anchor(), cli.PLUGIN_ROOT,
                                 name=SERVER_NAME, instructions=media_registry.INSTRUCTIONS)
    registry = media_registry.build_registry(ctx)
    from odoo_media import upgrade
    upgrade.start(ctx.version, cli.PLUGIN_ROOT)   # one-time pass on a new plugin version; never blocks serving
    logging.getLogger("odoo-local").info("starting %s v%s pid=%d tools=%s", SERVER_NAME, ctx.version,
                                         os.getpid(), registry.names())
    protocol.Server(registry, ctx, wire_out).serve(in_stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
