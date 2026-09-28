"""odoo_local - the `odoo-local` stdio MCP server package (live local Odoo instance lifecycle).

Kept import-free on purpose: the entry point imports `odoo_local.errors` on an interpreter too old
for the rest of the package (the PYTHON_TOO_OLD degraded mode), so this file must parse and run
everywhere.
"""

# MCP protocol revisions this server speaks, newest first. Defined HERE (not in protocol.py) so the
# PYTHON_TOO_OLD degraded loop in the entry point negotiates from the same list as the full server.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
