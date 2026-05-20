# JetBrains AI Assistant — Odoo Semantic MCP

JetBrains AI Assistant (2024.3+) supports connecting to external MCP servers.
Once configured, the 28 Odoo Semantic tools are available inside any JetBrains IDE
(IntelliJ IDEA, PyCharm, WebStorm, etc.).

## Server details

| Setting | Value |
|---------|-------|
| Server URL | `https://odoo-semantic.viindoo.com/mcp` |
| Auth header | `X-API-Key: <YOUR_API_KEY>` |
| Transport | HTTP (Streamable HTTP / SSE) |

Replace `<YOUR_API_KEY>` with your key (format: `osm_...`).

## Where to configure

In JetBrains IDE go to:
**Settings → Tools → AI Assistant → Model Context Protocol (MCP)**

Add a new server entry using the URL and header above.

For the authoritative configuration steps and supported IDE versions, see the
[JetBrains AI Assistant MCP documentation](https://www.jetbrains.com/help/idea/ai-assistant.html).

## Native plugin wrapper

A thin JetBrains plugin wrapper (for tighter IDE integration, e.g. project-aware
profiles, one-click install) is on the long-term roadmap but has no committed
delivery date. The HTTP MCP connection above works today.
