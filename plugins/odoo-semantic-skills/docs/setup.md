# Client Setup — Odoo Semantic MCP

This guide is for **end users** who want to connect their AI tool to an MCP server that an admin has already deployed.

> **For non-Claude-Code clients, nothing to install** — you only need a URL and an API key from your admin, then follow the section that matches your AI tool. (Claude Code users install the plugin — see the Claude Code section below.)

> **Snippet convention:** replace `<MCP_URL>` with the URL your admin sent (production:
> `https://odoo-semantic.viindoo.com/mcp`; local self-host: `http://127.0.0.1:8002/mcp`),
> and `<API_KEY>` with the raw key (`osm_xxxxxxxx...`) your admin issued (via the `/install/` page or Web UI).

> **The most common mistake:** each client stores MCP config in a **different file** with a **different schema**. Copy-pasting the wrong client's snippet means MCP **will not load — but the client will not report an error** (you only notice when a tool call returns "tool not found"). Each section below includes the canonical add command + JSON fallback + verify command + one client-specific pitfall.

> **Fastest path:** go to **https://odoo-semantic.viindoo.com/install/**, paste your API key, and the page generates the correct snippet for each client. The sections below are the official reference for advanced setup, troubleshooting, and auto-trust patterns.

---

## Claude Code

### Plugin install (recommended)

For Claude Code users, the plugin is the fastest path: it bundles the MCP server config, all 26 persona skills, and the setup command in one install.

#### 1. Add the marketplace (one-time)

```bash
claude plugin marketplace add Viindoo/claude-plugins --scope user
```

Or inside Claude Code:
```
/plugin marketplace add Viindoo/claude-plugins
```

#### 2. Install the plugin

```bash
claude plugin install odoo-semantic-skills@viindoo-plugins --scope user   # auto-pulls odoo-semantic-mcp
```

Or:
```
/plugin install odoo-semantic-skills@viindoo-plugins
```

Installing `odoo-semantic-skills` automatically pulls in the `odoo-semantic-mcp` plugin
(declared as a dependency), which provides the MCP server connection and the
`/odoo-semantic-mcp:connect` setup command. If you only need the MCP tools, install
`odoo-semantic-mcp@viindoo-plugins` on its own.

#### 3. Configure API key and server URL

On first use, Claude Code will prompt for:
- **API Key** — starts with `osm_`, get it from your admin or the [install page](https://odoo-semantic.viindoo.com/install/)
- **MCP Server URL** — default `https://odoo-semantic.viindoo.com/mcp` (change for self-hosted)

Or run the interactive setup command:
```
/odoo-semantic-mcp:connect
```

#### 4. Verify

```
Using odoo-semantic tools, show the full inheritance chain of sale.order in Odoo 17.0
```

Expected: tree output with module names, `Defined in:`, field counts.

#### Available persona skills

After install, 26 skills activate automatically:

| Skill | Persona | What it does |
|-------|---------|-------------|
| `odoo-risk-overview` | CEO / Exec | One-page upgrade-risk dashboard: deprecated-API counts, change blast radius, dependency health |
| `odoo-customization-inventory` | CEO / Exec | Executive inventory of every custom/distribution module, classified with business purpose and upgrade-risk flags |
| `odoo-override-finder` | Developer | Find the safe method to override, with the existing override chain and a ready-to-paste `super()` template |
| `odoo-deprecation-audit` | Developer | Scan a codebase for deprecated Odoo APIs before an upgrade, grouped by file with replacements and urgency |
| `odoo-version-diff` | Developer | Comprehensive API + feature diff between two Odoo versions (developer track + marketer track) |
| `odoo-coder` | Developer | Write production-ready Python/XML backend code, from a single computed field to a full module |
| `odoo-frontend-coder` | Developer | Write Odoo frontend JS for any version — legacy `web.Widget` (v8-v14) or OWL 2.x components (v15+) |
| `odoo-code-reviewer` | Developer | Review Odoo Python/JS/XML/OWL code for bugs, conventions, security, and performance with graded findings |
| `odoo-deploy-checklist` | Developer | Pre-deployment safety checklist across 8 domains (backup, migration, smoke tests, rollback, ...) |
| `odoo-feature-check` | Consultant | Answer "does standard Odoo already do this?" with module name, edition, and a client-ready verdict |
| `odoo-gap-analysis` | Consultant | Compare client requirements vs Odoo standard, ending in an effort matrix with day estimates |
| `odoo-discovery-summarize` | Consultant | Turn raw discovery-call notes into a structured customer profile with a fit score |
| `odoo-onboard` | Consultant | Bootstrap per-project Odoo context (version, custom modules, profile) so other skills skip setup |
| `odoo-feature-highlights` | Marketer | Generate business-language feature highlights for a version, ready for decks, blogs, or release notes |
| `odoo-addon-diff` | Marketer | Side-by-side CE vs EE vs custom-distribution comparison for a business domain, with upgrade recommendation |
| `odoo-content-draft` | Marketer | Draft channel-specific marketing content (LinkedIn, blog, YouTube script, email, landing copy) |
| `odoo-campaign-plan` | Marketer | Plan a multi-week, multi-channel marketing campaign with timeline, channel mix, KPIs, and owner map |
| `odoo-competitive-brief` | Strategist | Board-ready competitive brief on a named competitor: capability matrix, threat assessment, response strategy |
| `odoo-capability-proof` | Sales | Evidence-backed proof package that Odoo can meet a requirement, citing real modules and code |
| `odoo-objection-handler` | Sales | Evidence-based responses to capability objections using the Acknowledge / Counter / Affirm framework |
| `odoo-deal-followup` | Sales | Score deal health, recommend a next-best action, and draft a follow-up email |
| `odoo-router` | Utility | Silently route a vague Odoo request to the single best specialist skill, then confirm before running |
| `odoo-ui-reviewer` | Visual | Five-lens review of a rendered Odoo screen in a live browser — aesthetics, function, runtime stability, accessibility, performance — with screenshot/console/Lighthouse evidence |
| `odoo-ui-debug` | Visual | Root-cause a broken/misbehaving Odoo UI at runtime (console errors, failed requests, blank OWL renders, wrong CSS) and pinpoint the override point |
| `odoo-visual-regression` | Visual | Capture a screenshot baseline of one Odoo state and diff it against another (before/after upgrade, module install, theme change) with blast-radius assessment |
| `odoo-demo-recorder` | Visual | Record an MP4/GIF screen-capture of a scripted Odoo click-path for a demo, sales walkthrough, or marketing clip |

> **Visual skills need browser setup.** The four `Visual` skills above drive a live browser
> and depend on the bundled browser MCP servers + browser binaries. Run
> **`/odoo-semantic-skills:setup`** once to provision them — see
> [Visual stack / browser MCP setup](#visual-stack--browser-mcp-setup) below.

---

> **Other AI tools (Codex, Gemini, VS Code, Antigravity):** The plugin is Claude Code only. For other tools, follow the per-client MCP config sections below.

---

### Manual MCP setup (advanced / self-hosted)
<a id="manual-mcp-setup-advanced--self-hosted"></a>

Docs: <https://code.claude.com/docs/en/mcp>

Option 1 — CLI (recommended, official):
```bash
claude mcp add --scope user --transport http odoo-semantic <MCP_URL> \
    --header "X-API-Key: <API_KEY>"
```

Option 2 — JSON fallback (file `~/.claude.json`, **not** `~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "type": "http",
      "url": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" }
    }
  }
}
```

Verify: run `/mcp` in a live session, or `claude mcp list` from the shell. You should see `odoo-semantic … Connected`.

**Pitfall 1 (very common):** `~/.claude/settings.json` (for permissions/hooks) is **not** the same as `~/.claude.json` (for MCP servers). Older READMEs incorrectly referenced `settings.json` — MCP never loads from there. If you followed an old README: remove the `mcpServers.odoo-semantic` entry from `~/.claude/settings.json`, then re-run the CLI command above.

**Pitfall 2:** After adding, you must **restart Claude Code** — new entries do not load at runtime.

### Auto-trust: skip permission prompts
<a id="claude-code-auto-trust"></a>

> **If you installed via the plugin:** `/odoo-semantic-mcp:connect` already adds this entry to `~/.claude/settings.json` automatically (idempotent, with backup, no side effects on other keys). Confirm at the final prompt — you can skip the rest of this section. If you declined: follow the manual snippet below.

Manual snippet (for users who ran `claude mcp add` directly, without the plugin):

```json
{
  "permissions": {
    "allow": ["mcp__odoo-semantic"]
  }
}
```

> If the file already has `permissions.allow`, append the string `"mcp__odoo-semantic"` to the array.
> A wildcard without a tool name pre-approves all tools on this server.

---

## Visual stack / browser MCP setup
<a id="visual-stack--browser-mcp-setup"></a>

The four `Visual` skills (`odoo-ui-reviewer`, `odoo-ui-debug`, `odoo-visual-regression`,
`odoo-demo-recorder`) and the `odoo-ui-reviewer` agent drive a **rendered Odoo screen in a
live browser**. They depend on three browser MCP servers — `chrome-devtools`, `playwright`,
and `pagecast` (local stdio `npx` servers) — plus browser binaries and `ffmpeg`.

### One command: `/odoo-semantic-skills:setup`

Inside Claude Code, run it once:

```
/odoo-semantic-skills:setup
```

It is **idempotent and extensible** — re-running only applies what is missing, and it drives
a registry of numbered step scripts (`scripts/setup-steps/`), so new capabilities are
drop-in. What it does:

1. **Browser MCP** — registers `chrome-devtools`, `playwright`, `pagecast` into Claude Code,
   Codex CLI, and Gemini CLI (cross-runtime).
2. **Browser deps** — checks Node >= 20, installs Playwright Chromium, checks `ffmpeg`.
3. **Permissions** — auto-allows the browser MCP tools in Claude permissions.
4. **Instance profile** — discovers local Odoo repos and writes `.odoo-ai/instances.toml`.
5. **Instance spin-up** (optional) — launches a declared Odoo instance and waits for HTTP 200.

> For Claude Code, the three browser MCP servers also load automatically from the plugin's
> bundled `.mcp.json` once the plugin is installed. The setup command additionally wires the
> **other** runtimes (Codex, Gemini) and installs the browser dependencies, which the bundle
> alone does not.

A **SessionStart** hint (read-only, never installs or blocks) nudges you to run
`/odoo-semantic-skills:setup` whenever a dependency is missing.

### Cross-runtime MCP wiring (what the setup writes)

Each runtime stores browser MCP config in a **different file with a different schema** — the
setup command writes the correct shape for each, merging idempotently into existing config:

| Runtime | Config file | Schema |
|---------|-------------|--------|
| Claude Code | `~/.claude.json` (key `mcpServers`) | JSON — `{ "command": "npx", "args": [...] }` per server |
| Codex CLI | `~/.codex/config.toml` | TOML — `[mcp_servers.<name>]` with `command` / `args` |
| Gemini CLI | `~/.gemini/settings.json` (key `mcpServers`) | JSON — per-server entry plus `"trust": true` to skip prompts |

The browser servers are local stdio `npx` servers (no API key needed), unlike the
`odoo-semantic` HTTP server documented above — so this wiring is independent of the
`/odoo-semantic-mcp:connect` flow.

---

## OpenAI Codex CLI

Docs: <https://developers.openai.com/codex/mcp>

Edit `~/.codex/config.toml` (the `codex mcp add` CLI does not support a `--header` flag — you must edit the TOML directly):
```toml
[mcp_servers.odoo-semantic]
url = "<MCP_URL>"
http_headers = { "X-API-Key" = "<API_KEY>" }
```

Restart Codex. Verify: `codex mcp list`.

**Pitfall:** the key must be `http_headers` (snake_case, plural). Writing `headers = ...` causes Codex to silently ignore it and send no auth header, resulting in a 401 from the MCP server.

### Auto-trust: skip permission prompts
<a id="codex-cli-auto-trust"></a>

> **Trade-off**: Codex CLI has no per-server pre-approval mechanism. Each tool will prompt for confirmation on first use. This is a limitation of the Codex CLI, not the server. The only workaround is setting `approval_policy = "never"` in config — but that affects all tools, which is not recommended.

API key via environment variable (cleaner than hardcoding in TOML):

```bash
echo 'export ODOO_SEMANTIC_KEY="YOUR_API_KEY"' >> ~/.bashrc
```

In `~/.codex/config.toml`:
```toml
[mcp_servers.odoo-semantic]
url = "https://odoo-semantic.viindoo.com/mcp"
env_http_headers = { "X-API-Key" = "ODOO_SEMANTIC_KEY" }
```

---

## Google Gemini CLI

Docs: <https://github.com/google-gemini/gemini-cli/blob/main/docs/tools/mcp-server.md>

Edit `~/.gemini/settings.json` (user-global) or `.gemini/settings.json` (project):
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "httpUrl": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" },
      "timeout": 10000
    }
  }
}
```

Restart `gemini`. Verify: `/mcp` in the CLI.

**Pitfall:** the property must be `httpUrl` (not `url`). Using `url` causes Gemini to treat it as the deprecated SSE transport, resulting in a handshake hang or failure.

### Auto-trust: skip permission prompts
<a id="gemini-cli-auto-trust"></a>

Add `"trust": true` to the server entry in `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "odoo-semantic": {
      "httpUrl": "https://odoo-semantic.viindoo.com/mcp",
      "headers": { "X-API-Key": "YOUR_API_KEY" },
      "trust": true
    }
  }
}
```

> `"trust": true` bypasses all confirmation prompts for this server.

---

## VS Code (built-in MCP, v1.99+)

Docs: <https://code.visualstudio.com/docs/copilot/reference/mcp-configuration>

Command Palette (`Ctrl/Cmd+Shift+P`) → **`MCP: Open User Configuration`** — opens `mcp.json`:
```json
{
  "servers": {
    "odoo-semantic": {
      "type": "http",
      "url": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" }
    }
  }
}
```

Click the **Start** codelens that appears on the server block, or reload the window.

**Pitfall:** the top-level key is `servers` (not `mcpServers` as in Claude/Gemini/Antigravity). `type` must be exactly `"http"` (not `"streamable-http"`). Do not put MCP servers into `settings.json` — use the separate `mcp.json` file.

### Auto-trust: skip permission prompts
<a id="vs-code-auto-trust"></a>

VS Code has no config flag for pre-trusting a server. Click **"Always allow for this server"** in the Chat UI on the first tool call.

**One-click install URL** (paste into a browser; VS Code handles the rest):

```
vscode:mcp/install?%7B%22name%22%3A%22odoo-semantic%22%2C%22type%22%3A%22http%22%2C%22url%22%3A%22https%3A%2F%2Fodoo-semantic.viindoo.com%2Fmcp%22%2C%22headers%22%3A%7B%22X-API-Key%22%3A%22YOUR_API_KEY%22%7D%7D
```

JSON pre-encoded (replace `YOUR_API_KEY`):
```json
{"name":"odoo-semantic","type":"http","url":"https://odoo-semantic.viindoo.com/mcp","headers":{"X-API-Key":"YOUR_API_KEY"}}
```

> VS Code's URL handler behavior with the `headers` field is not fully documented. If the tool returns 401 after install, add `headers` manually to `.vscode/mcp.json`.

---

## Google Antigravity

Docs: <https://antigravity.google/docs/mcp>

IDE → **Manage MCP Servers → View raw config** — or edit `~/.gemini/antigravity/mcp_config.json` directly:
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "serverUrl": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" }
    }
  }
}
```

Save → click **Refresh** in the MCP panel.

**Pitfall:** the property must be `serverUrl` (camelCase, not `url` or `httpUrl`). The file lives under `~/.gemini/antigravity/` — it shares a path prefix with Gemini CLI but has a different schema.

### Auto-trust: skip permission prompts
<a id="antigravity-auto-trust"></a>

After adding the server: go to **... → MCP Servers** → find `odoo-semantic` → add the allow-list pattern `mcp(odoo-semantic.*)` to pre-approve all tools.

> Antigravity has only a global config, no project-level config. The API key is stored in plaintext in `~/.gemini/antigravity/mcp_config.json` — ensure the file has `600` permissions.

---

## Session Context Setup (v0.5+) — `set_active_version` / `set_active_profile`

Starting in v0.5.0 the MCP server supports **sticky session context** so you stop repeating `odoo_version="17.0"` on every call. Run `set_active_version` once and the value is remembered for 24h per API key. Similarly `set_active_profile` pins the tenant profile.

**Recommended startup flow** for any AI client (Claude Code, Codex, Gemini, VS Code, Antigravity):

```
1. list_available_versions()    # see which Odoo versions the server has data for
2. set_active_version("17.0")   # pin the version for this session (24h TTL)
3. list_available_profiles()    # see which tenant profiles exist (optional)
4. set_active_profile("viindoo-internal")   # pin tenant profile (optional)
5. <any tool call with odoo_version omitted>   # falls back to the pinned value
```

After step 2, calling `model_inspect(model="sale.order", method="summary")` (no `odoo_version=` arg) returns results for `17.0`. Override at any time by passing `odoo_version=` explicitly on a single call (one-off; does **not** clear the sticky value).

> See [ADR-0029](https://odoo-semantic.viindoo.com/docs/adr/0029-implicit-session-context) for the TTL design and per-key keying rationale.

---

## MCP Resources (`odoo://` URI scheme, v0.5+)

In addition to the tool calls, the server exposes **7 MCP Resources** addressable via stable URIs — preferred when the caller already knows the entity ID and just wants the canonical record (read-only, bookmark-friendly, no parameters):

| URI template | Returns |
|--------------|---------|
| `odoo://{version}/model/{name}` | Model record (inheritance, field/method counts, modules) |
| `odoo://{version}/field/{model}/{field}` | Field record (type, compute, definition module) |
| `odoo://{version}/method/{model}/{method}` | Method record (override chain, super_ratio) |
| `odoo://{version}/module/{name}` | Module record (manifest, defines/extends counts) |
| `odoo://{version}/view/{xmlid}` | View record (xpath chain, inherit_id) |
| `odoo://{version}/pattern/{name}` | Pattern catalogue entry (code snippet + gotchas) |
| `odoo://{version}/stylesheet/{module}/{file_path*}` | Stylesheet record (selectors, imports, variables) |

**Example:**

```
odoo://17.0/model/sale.order
odoo://17.0/field/sale.order/amount_total
odoo://17.0/view/sale.view_order_form
```

Clients that implement the MCP `resources/list` and `resources/read` flows surface these as bookmark-style references. See [ADR-0030](https://odoo-semantic.viindoo.com/docs/adr/0030-mcp-resources-uri-scheme) for the URI grammar and authorization model (same `X-API-Key` header as tool calls).

---

## Superset Tools — server v0.11.1 Reference

The server exposes **24 tools** at v0.11.1. The v0.7 surface added 2 stylesheet tools
(`resolve_stylesheet`, `find_style_override`) on top of the v0.6 base; v0.8 (M10.5 Phase 2)
added 4 ORM-validation tools; v0.10.0 added `module_inspect(method='dependencies')`. The 10
flat `resolve_*` / `list_*` tools that existed in v0.4-v0.5 were deprecated in v0.5 and
**removed in v0.6** — they no longer exist on the server. If you encounter prompts or
snippets that reference the old names, replace them with the supersets below.

> The old `resolve_*` / `list_*` tools are gone. Use these supersets instead:

| Superset tool | Use case | Valid `method` values |
|---------------|----------|-----------------------|
| `model_inspect(model, method, ...)` | Model-level inspection: summary, field/method/view inventory | `summary` · `fields` · `methods` · `views` · `field` · `method` |
| `module_inspect(name, method, ...)` | Module-level inventory: manifest, views, OWL, QWeb, JS patches, dependencies | `summary` · `views` · `owl` · `qweb` · `js` · `dependencies` |
| `entity_lookup(kind, ...)` | Single entity drill-down by ID | kind: `field` · `method` · `view` |

### ORM-validation tools (server v0.8.0+ — M10.5 Phase 2)

Static checks against the indexed graph — run them before an AI client suggests a domain,
`@api.depends`, or relational field so hallucinated paths/operators are caught up front:

| Tool | Use case |
|------|----------|
| `resolve_orm_chain(model, dotted_path, odoo_version="auto")` | Walk a dotted field path; return the terminal type or the first broken hop |
| `validate_domain(model, domain, odoo_version="auto")` | Validate domain field-paths + operators (operators are **version-aware**) |
| `validate_depends(model, method, odoo_version="auto")` | Validate a compute method's indexed `@api.depends` paths |
| `validate_relation(model, field, target_model, odoo_version="auto")` | Assert a relational field's comodel matches the expected target |

**Full side-by-side migration guide:** see the server [CHANGELOG](https://odoo-semantic.viindoo.com/changelog).

---

## Verify After Install — Natural-Language Prompts

After adding the server, type one of the prompts below into your AI tool — the agent should automatically invoke the `odoo-semantic` MCP server and call `model_inspect`. If the agent returns a generic textbook description of `sale.order` instead of citing real module names and an `odoo_version` from the index, the MCP server has not loaded correctly — return to the section for your client.

- *"Using the odoo-semantic tools, show me the full inheritance chain of `sale.order` in Odoo 17.0 — which modules extend it?"*
- *"Inspect the model `sale.order` for version 17.0 and list all fields added by extension modules."*

**Signs the MCP is working correctly:**
- Concrete module names from the index (`sale`, `sale_management`, `website_sale`, ...)
- Tree format output `+-- ... L--`
- `Defined in: [<repo>] <module>` and `Inherits from: ...` blocks
- Specific counts such as `Fields: 148` / `Methods: 394` (not round estimated numbers)

**Signs the agent is answering from general knowledge (MCP not active):**
- Long prose response about "sale.order is a model in Odoo's sales module..."
- No module names from an indexed codebase
- No tree format
- No acknowledgment of having called a tool
