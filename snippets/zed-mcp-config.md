# Zed Editor — Odoo Semantic MCP Configuration

[Zed](https://zed.dev) supports MCP servers via `context_servers` in its `settings.json`.
Once configured, all Odoo Semantic tools are available inline in Zed's AI chat and
command palette.

## Server details

| Setting | Value |
|---------|-------|
| Server URL | `https://odoo-semantic.viindoo.com/mcp` |
| Auth header | `X-API-Key: <YOUR_API_KEY>` |
| Transport | HTTP (Streamable HTTP / SSE) |

Replace `<YOUR_API_KEY>` with your key (format: `osm_...`).

## Configuration

### Option 1: Zed `settings.json` (recommended)

Add the following to your Zed settings (`Cmd/Ctrl+Shift+P → Open Settings`):

```json
{
  "context_servers": [
    {
      "name": "odoo-semantic",
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/adapter-stdio-http",
        "--url",
        "https://odoo-semantic.viindoo.com/mcp",
        "--header",
        "X-API-Key: YOUR_API_KEY_HERE"
      ]
    }
  ]
}
```

> **Note:** Replace `YOUR_API_KEY_HERE` with your actual API key. The `npx` command
> installs the stdio→HTTP adapter on first run.

### Option 2: Raw `context_servers` JSON snippet

A copy-ready JSON file is provided at
[`snippets/zed-mcp.json`](snippets/zed-mcp.json). Import it into your Zed
`settings.json` under the `context_servers` key.

## Verification

After adding the configuration:

1. Restart Zed (or reload settings)
2. Open the AI Chat panel (`Cmd/Ctrl+L`)
3. Type `@odoo-semantic` — the server tools should appear in the autocomplete list

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `@odoo-semantic` not found | Verify API key format (`osm_...`) and server URL |
| `npx` not found | Ensure Node.js >= 18 is installed and in `PATH` |
| Tools load but return errors | Check server health at `https://odoo-semantic.viindoo.com/health` |

For the latest Zed MCP documentation, see
[Zed's Context Servers docs](https://zed.dev/docs/ai/context-servers).
