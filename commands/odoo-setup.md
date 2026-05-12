# /odoo-semantic:setup

Interactive setup command for Odoo Semantic MCP.

## Steps

1. Check if `~/.claude.json` exists and is readable
2. Ask user: "Enter your MCP server URL [default: https://odoo-semantic.viindoo.com:9999/mcp]:"
3. Ask user: "Paste your API key (starts with osm_):"
4. Validate key format matches `^osm_[A-Za-z0-9]+$`
5. Add or update `mcpServers.odoo-semantic` in `~/.claude.json`:
   ```json
   {
     "type": "http",
     "url": "<entered URL>",
     "headers": { "X-API-Key": "<entered key>" }
   }
   ```
6. Call `resolve_model` with model="res.partner" version="17.0" to validate connectivity
7. If validation passes: print "✓ Connected! 14 MCP tools available."
8. List all 11 skill names from this plugin

## Error handling

- If `~/.claude.json` is missing: create it with empty `{}`
- If API key validation fails: print error and re-prompt
- If connectivity check fails: print server URL and suggest checking VPN/firewall
