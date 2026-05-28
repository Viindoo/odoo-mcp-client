# Roadmap

This roadmap covers the **client** layer (this repository). The semantic backend has
its own roadmap, accessible after registration at
[odoo-semantic.viindoo.com](https://odoo-semantic.viindoo.com/).
Items are directional, not commitments, and reflect publicly announced milestones only.

## Now

- **Tool-surface parity with server v0.5** — skills and snippets reference the M11
  superset tools (`model_inspect`, `module_inspect`, `entity_lookup`) and the 7
  `odoo://` MCP Resources (ADR-0028 / ADR-0029 / ADR-0030).
- **Marketplace publishing pipeline** — automatic SHA pinning into
  `Viindoo/claude-plugins` on each release.

## Next

- **More client snippets** — Continue.dev (`continue-dev-mcp.yaml`) and a JetBrains AI
  Assistant config placeholder, alongside the existing Cursor / ChatGPT / Gemini snippets.
- **v0.6 deprecation cleanup** — once the server removes the 10 legacy
  `resolve_*` / `list_*` tools, drop their mentions from skills and snippets.

## Later / exploring

- **JetBrains plugin wrapper** — a thin native wrapper once demand is clear.
- **PyPI distribution** — `pip install`-able client for non-Claude IDEs.
- **Decouple client from server tool surface** — intent-only skill descriptions +
  build-time generator that reads the server's `tools/list` response and routing
  matrix to emit adapter snippets (Cursor/Gemini/OpenAI) automatically. Eliminates
  manual routing duplication; the server-side MCP Prompt becomes the SSOT for routing
  logic, and the client never needs a hand-rolled classifier agent again.

## Out of scope for this repo

- Indexer, graph/vector storage, MCP server logic, billing, and the web UI all live
  in the AGPL server repository.

Have an idea? Open a [feature request](https://github.com/Viindoo/odoo-mcp-client/issues).
