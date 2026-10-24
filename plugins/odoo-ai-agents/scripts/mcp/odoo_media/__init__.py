"""odoo_media - the `odoo-media` stdio MCP server package: narration speech (text-to-speech,
speech-to-text, the round-trip probe) and YouTube publishing, the two surfaces that need a value the
operator configured through the plugin's options (Claude Code's own dialog). The values reach THIS
process as environment variables that the plugin's .mcp.json maps from `${user_config.*}`; no
script an agent runs through Bash ever sees them, and no tool result carries one.

Reuses the odoo-local protocol frame (scripts/mcp/odoo_local/protocol.py): wire discipline,
schema validation, the long-running lane with per-call cancellation, the error envelope.
Import-free on purpose (the entry point reads SUPPORTED_PROTOCOL_VERSIONS in degraded mode).
"""

SERVER_NAME = "odoo-media"
