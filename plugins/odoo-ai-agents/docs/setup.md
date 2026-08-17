# Client Setup - Odoo Semantic MCP

This guide is for **end users** who want to connect their AI tool to an MCP server that an admin has already deployed.

> **For non-Claude-Code clients, nothing to install** - you only need a URL and an API key from your admin, then follow the section that matches your AI tool. (Claude Code users install the plugin - see the Claude Code section below.)

> **Snippet convention:** replace `<MCP_URL>` with the URL your admin sent (production:
> `https://odoo-semantic.viindoo.com/mcp`; local self-host: `http://127.0.0.1:8002/mcp`),
> and `<API_KEY>` with the raw key (`osm_xxxxxxxx...`) your admin issued (via the `/install/` page or Web UI).

> **The most common mistake:** each client stores MCP config in a **different file** with a **different schema**. Copy-pasting the wrong client's snippet means MCP **will not load - but the client will not report an error** (you only notice when a tool call returns "tool not found"). Each section below includes the canonical add command + JSON fallback + verify command + one client-specific pitfall.

> **Fastest path:** go to **https://odoo-semantic.viindoo.com/install/**, paste your API key, and the page generates the correct snippet for each client. The sections below are the official reference for advanced setup, troubleshooting, and auto-trust patterns.

---

## Claude Code

### First-time setup flow - two steps, different scopes

These two steps are easy to confuse. Only the first is required:

| Step | Command / skill | Scope | When |
|------|-----------------|-------|------|
| 1. Connect the MCP server | `/odoo-semantic-mcp:connect` | Once per machine | **Required** - registers server URL + API key so `mcp__odoo-semantic__*` tools load |
| 2. Declare an instance | `/odoo-ai-agents:odoo-setup` | Once per repo/series | **Optional** - browser MCP + Playwright + a local Odoo instance declared in `$ODOO_AI_HOME/instances.toml`, only for the `Visual` skills or a live run |

Step 1 is covered below. Step 2 is in [Visual stack / browser MCP setup](#visual-stack-browser-mcp-setup). Without it, every `odoo-*` skill still resolves the Odoo series/profile/scope from the checkout the first time you invoke it in a new repo.

> **Version gate - Claude Code >= 2.1.172.** The coding workflow uses NESTED subagent dispatch:
> `odoo-coding` launches an `odoo-coder` coordinator per NODE (every node, not just full-stack),
> which itself launches its teammates - `odoo-test-writer` (RED test first), then `odoo-backend-coder`
> and/or `odoo-frontend-coder` (one agent level deeper). Nested dispatch requires
> Claude Code 2.1.172+ (the platform depth cap is 5). The `/odoo-ai-agents:odoo-setup` prereq check
> (`05-prereq-check.sh`) probes `claude --version` and prints this gate.

### Plugin install (recommended)

For Claude Code users, the plugin is the fastest path: it bundles the MCP server config, all 51 skills, and the setup command in one install.

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
claude plugin install odoo-ai-agents@viindoo-plugins --scope user   # auto-pulls odoo-semantic-mcp
```

Or:
```
/plugin install odoo-ai-agents@viindoo-plugins
```

Installing `odoo-ai-agents` automatically pulls in the `odoo-semantic-mcp` plugin
(declared as a dependency), which provides the MCP server connection and the
`/odoo-semantic-mcp:connect` setup command. If you only need the MCP tools, install
`odoo-semantic-mcp@viindoo-plugins` on its own.

#### 3. Configure API key and server URL

On first use, Claude Code will prompt for:
- **API Key** - starts with `osm_`, get it from your admin or the [install page](https://odoo-semantic.viindoo.com/install/)
- **MCP Server URL** - default `https://odoo-semantic.viindoo.com/mcp` (change for self-hosted)

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

After install, 51 skills activate automatically:

> Persona labels are the navigation buckets defined in the [README skill table](../README.md#skills-51) - the single source of truth for the skill-to-persona mapping. The five role guides in [`personas/`](personas/) (Manager/CEO, Developer, Consultant, Marketer, Sales) group these buckets. This table is a curated subset; all 51 skills auto-activate on install.

| Skill | Persona | What it does |
|-------|---------|-------------|
| `odoo-risk-overview` | Strategist / CEO | One-page upgrade-risk dashboard: deprecated-API counts, change blast radius, dependency health |
| `odoo-customization-inventory` | Strategist / CEO | Executive inventory of every custom/distribution module, classified with business purpose and upgrade-risk flags |
| `odoo-competitive-brief` | Strategist | Board-ready competitive brief on a named competitor: capability matrix, threat assessment, response strategy |
| `odoo-override-finding` | Engineer | Find the safe method to override, with the existing override chain and a ready-to-apply `super()` template |
| `odoo-deprecation-audit` | Engineer | Scan a codebase for deprecated Odoo APIs before an upgrade, grouped by file with replacements and urgency |
| `odoo-deploy-checklist` | Engineer | Pre-deployment safety checklist across 8 domains (backup, migration, smoke tests, rollback, ...) |
| `odoo-forward-port` | Coder / Engineer | Continuous/one-shot Odoo forward-port (merge-keep-SHA, per-commit intent extract, adaptive test forward); output under `<ISOLATE_DIR>/forward-port/`; invoke via `/odoo-forward-port` or plain-language intent |
| `odoo-version-diff` | Engineer + Marketer | Comprehensive API + feature diff between two Odoo versions (developer track + marketer track) |
| `odoo-coding` | Coder | The single coding front door - write production-ready backend (Python/XML) AND frontend (JS/OWL/QWeb/SCSS) code, from a single computed field to a multi-module full-stack feature; scopes the change and sequences the backend + frontend coder agents |
| `odoo-i18n` | Coder / Engineer | Export .pot templates, non-destructively merge .po translations, dispatch hand-translation for one or more target languages in a single run (no built-in default - resolved from the request, `$ODOO_AI_HOME/i18n.json`, on-disk `.po` filenames, or the live instance, else `NEEDS_CONTEXT`), and audit cross-module term consistency - the dedicated i18n cluster and the translation step dispatched by forward-port and other workflows |
| `odoo-code-review` | Code-Reviewer | Review Odoo Python/JS/XML/OWL code for bugs, conventions, security, and performance with graded findings |
| `odoo-feature-check` | Pre-Sales Consultant | Answer "does standard Odoo already do this?" with module name, edition, and a client-ready verdict |
| `odoo-gap-analysis` | Pre-Sales Consultant | Compare client requirements vs Odoo standard, ending in an effort matrix with day estimates |
| `odoo-capability-proof` | Pre-Sales Consultant | Evidence-backed proof package that Odoo can meet a requirement, citing real modules and code |
| `odoo-addon-diff` | Pre-Sales Consultant | Side-by-side CE vs EE vs custom-distribution comparison for a business domain, with upgrade recommendation |
| `odoo-objection-handling` | Sales AE | Evidence-based responses to capability objections using the Acknowledge / Counter / Affirm framework |
| `odoo-deal-followup` | Sales AE | Score deal health, recommend a next-best action, and draft a follow-up email |
| `odoo-discovery-summary` | Sales AE | Turn raw discovery-call notes into a structured customer profile with a fit score |
| `odoo-feature-highlights` | Marketer | Generate business-language feature highlights for a version, ready for decks, blogs, or release notes |
| `odoo-content-draft` | Marketer | Draft channel-specific marketing content (LinkedIn, blog, YouTube script, email, landing copy) |
| `odoo-campaign-plan` | Marketer | Plan a multi-week, multi-channel marketing campaign with timeline, channel mix, KPIs, and owner map |
| `odoo-intake` | Onboarding / Concierge | Universal front door - brainstorms when vague, fast-paths when clear, always gates with a Proposed Plan before execution |
| `odoo-ui-review` | Coder / Visual | Five-lens review of a rendered Odoo screen in a live browser - aesthetics, function, runtime stability, accessibility, performance - with screenshot/console/Lighthouse evidence |
| `odoo-debug` | Coder | Front-door orchestrator for all Odoo debugging - scientific method; dispatches specialist debug agents (backend/UI) |
| `odoo-visual-regression` | Coder / Visual | Capture a screenshot baseline of one Odoo state and diff it against another (before/after upgrade, module install, theme change) with blast-radius assessment |
| `odoo-demo-recording` | Coder / Visual | Record an MP4/GIF screen-capture of a scripted Odoo click-path for a demo, sales walkthrough, or marketing clip |

> **Visual skills need browser setup.** The three `Coder / Visual` skills above (`odoo-ui-review`, `odoo-visual-regression`, `odoo-demo-recording`) drive a live browser
> and depend on the bundled browser MCP servers + browser binaries. Run
> **`/odoo-ai-agents:odoo-setup`** once to provision them - see
> [Visual stack / browser MCP setup](#visual-stack-browser-mcp-setup) below.

---

> **Other AI tools (Codex, Gemini, VS Code, Antigravity, Windsurf, Zed, JetBrains Junie):** The plugin is Claude Code only. For other tools, follow the per-client MCP config sections below.

---

### Manual MCP setup (advanced / self-hosted)
<a id="manual-mcp-setup-advanced--self-hosted"></a>

Docs: <https://code.claude.com/docs/en/mcp>

Option 1 - CLI (recommended, official):
```bash
claude mcp add --scope user --transport http odoo-semantic <MCP_URL> \
    --header "X-API-Key: <API_KEY>"
```

`claude mcp add` has **no `--timeout` flag**, so after adding, also set a
per-tool-call timeout to stop a hung server from blocking the agent (see the
timeout note below) - edit the `~/.claude.json` entry to add `"timeout": 90000`,
or just run `/odoo-semantic-mcp:connect`, which does this for you.

Option 2 - JSON fallback (file `~/.claude.json`, **not** `~/.claude/settings.json`):
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "type": "http",
      "url": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" },
      "timeout": 90000
    }
  }
}
```

> **Why `timeout`?** Claude Code's default per-tool-call timeout
> (`MCP_TOOL_TIMEOUT`) is ~28 hours. The server already bounds each query (~30 s) and
> rejects fast under load, so a request won't hang on its own; the client
> `"timeout": 90000` (90 s, in ms) is a defensive backstop capping the wait if a
> transport-level stall slips past the server bound. Honored per-server in
> `~/.claude.json` / `.mcp.json` (min 1000 ms; HTTP 60 s first-byte floor). Drop to
> `60000` for the fastest fallback, or raise it for very large `impact_analysis` calls.

Verify: run `/mcp` in a live session, or `claude mcp list` from the shell. You should see `odoo-semantic … Connected`.

**Pitfall 1 (very common):** `~/.claude/settings.json` (for permissions/hooks) is **not** the same as `~/.claude.json` (for MCP servers). Older READMEs incorrectly referenced `settings.json` - MCP never loads from there. If you followed an old README: remove the `mcpServers.odoo-semantic` entry from `~/.claude/settings.json`, then re-run the CLI command above.

**Pitfall 2:** After adding, you must **restart Claude Code** - new entries do not load at runtime.

### Auto-trust: skip permission prompts
<a id="claude-code-auto-trust"></a>

> **If you installed via the plugin:** `/odoo-semantic-mcp:connect` already adds this entry to `~/.claude/settings.json` automatically (idempotent, with backup, no side effects on other keys). Confirm at the final prompt - you can skip the rest of this section. If you declined: follow the manual snippet below.

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

The three `Visual` skills (`odoo-ui-review`, `odoo-visual-regression`,
`odoo-demo-recording`) and the `odoo-ui-reviewer` agent drive a **rendered Odoo screen in a
live browser**. They depend on the browser MCP families - three backends (`chrome-devtools`,
`playwright`, `pagecast`), each with a headless default and a `-headed` variant (local stdio
`npx` servers) - plus browser binaries and `ffmpeg`.

Only ONE family is **eager**: the headless `chrome-devtools`, bundled in the plugin's
`.mcp.json` and auto-loaded. The other five are **opt-in** so a plain session never launches
browser processes it does not need; `/odoo-ai-agents:odoo-setup browser` wires them on demand
(step 10 for Codex/Gemini, step 12 for Claude at user scope). Package versions are pinned (no
`@latest`).

> **Opt-out (browser-free host).** To also stop the eager `chrome-devtools` from loading, add
> `"disabledMcpjsonServers": ["chrome-devtools"]` to your Claude settings (`~/.claude/settings.json`)
> and simply do not run the opt-in wiring (step 12).

> **Install once (disk) vs register-to-run (RAM per open session).** These are two separate
> setup steps with two separate cost profiles:
> - **Install** (`/odoo-ai-agents:odoo-setup browser`, step 20) pre-installs the 3 pinned npm
>   packages behind the 6 families - and the Playwright Chromium browser - **on disk only**.
>   This warms npm's local cache so a later real spawn has zero download latency. It never
>   launches a server and costs **disk, never RAM**; run it once per machine (idempotent - a
>   package already cached is skipped).
> - **Register** (steps 10/12, above) wires a family into your MCP client's config so it can be
>   spawned. A registered server only actually runs - and only then costs RAM - while a session
>   that uses it is open; closing the session frees that RAM. Registering does **not** by
>   itself consume any RAM.

### Per-runtime native provisioning

Each supported AI runtime ships the EAGER `chrome-devtools` family as part of the plugin
bundle; the five opt-in families are wired on demand. For most users, install the plugin and
the eager server is wired automatically:

| Runtime | Bundle file | Install command | Dedup behaviour |
|---------|-------------|-----------------|-----------------|
| **Claude Code** | `.mcp.json` (auto-loaded on plugin install; eager `chrome-devtools` only) | `claude plugin install odoo-ai-agents@viindoo-plugins` | Claude deduplicates by command/endpoint: a same-command server already in your config simply wins; the bundled copy is skipped - normal, not an error. No extra step. |
| **Gemini CLI** | `gemini-extension.json` (in the plugin directory) | `gemini extensions install <your-clone>/plugins/odoo-ai-agents` (or `...link ...` for live dev) | Dedup is by server **name**: a same-named server already in `~/.gemini/settings.json` wins (no error). **Important:** Gemini cannot install an extension from a subdirectory of a git repo - use the local path after cloning, not a raw GitHub URL. The `trust` field is not permitted in the extension manifest. |
| **Codex CLI** | `.codex-plugin/plugin.json` | `codex plugin marketplace add <marketplace>` then `codex plugin add odoo-ai-agents@<marketplace>` (marketplace.json is to be published as a separate distribution step; the manifest ships now) | Same dedup-by-name behaviour as Claude. |

> **Fallback for Codex / Gemini non-native installs:** run
> `/odoo-ai-agents:odoo-setup runtime` - it writes the correct config for each
> runtime idempotently without touching the rest of the setup steps.

### One command: `/odoo-ai-agents:odoo-setup`

Inside Claude Code, run it once:

```
/odoo-ai-agents:odoo-setup
```

It is **idempotent and extensible** - re-running only applies what is missing, and it drives
a registry of numbered step scripts (`scripts/setup-steps/`), so new capabilities are
drop-in. What it does:

1. **Browser MCP** - wires the browser families on demand: step 10 registers them into Codex
   CLI and Gemini CLI; step 12 registers Claude's five opt-in families at user scope. Claude's
   eager `chrome-devtools` comes from the bundled `.mcp.json`, so neither step writes it to
   `~/.claude.json`. Packages are pinned (no `@latest`).
2. **Browser deps** - checks Node >= 20; pre-installs the 3 pinned browser MCP packages ON
   DISK (npm cache warm - install only, never launched: disk cost, zero RAM cost, and strictly
   separate from step 12's register/run); installs Playwright Chromium; checks `ffmpeg`.
3. **Permissions** - auto-allows the browser MCP tools in Claude permissions
   (`30-permissions`), plus the narrow set of state-root Bash/Read/Edit
   rules the planning pipeline needs to resolve and write under `$ODOO_AI_HOME`
   without a per-call prompt (`32-permissions-state-root`). The state-root
   write rules cover ONLY `$ODOO_AI_HOME/projects/**` - both the plan (SHARE)
   and the per-worktree worklog (ISOLATE) resolve nested under it, so there is
   no separate top-level `worklog/` surface to grant. They exclude `bin/`,
   `venvs/`, `node_tools/`, `setup-scripts/`, `runtime/`, and `instances.toml`
   (code-execution-adjacent paths, never auto-granted). Because permissions
   are finalized before SessionStart hooks run, a first apply needs ONE Claude
   Code restart (or a new session) to take effect.
4. **Instance profile** - discovers local Odoo repos and writes the machine-global `$ODOO_AI_HOME/instances.toml` (any agent on this host resolves instances regardless of working directory).
   Also seeds `$ODOO_AI_HOME/i18n.json` (`{"default_languages":[]}`, empty - no locale is assumed on
   your behalf) - the machine-global language registry for the odoo-i18n cluster; edit to add your
   own target languages, e.g. `["vi_VN","en_US"]`.
5. **DB local auth** (`48-db-local-auth`) - lets Odoo reach the declared PostgreSQL role on a local
   cluster without a stored password, via a managed block in that cluster's `pg_hba.conf`; reverted
   with `48-db-local-auth.sh revert`.
6. **Instance spin-up** (optional) - launches a declared Odoo instance and waits for HTTP 200.

A **SessionStart** hint (read-only, never installs or blocks) nudges you to run
`/odoo-ai-agents:odoo-setup` whenever a dependency is missing.

### Cross-runtime MCP wiring (what `/odoo-setup runtime` writes)

Each runtime stores browser MCP config in a **different file with a different schema**.
When the per-runtime native bundle is not used, the setup command writes the correct
shape for each, merging idempotently into existing config:

| Runtime | Config file | Schema | Note |
|---------|-------------|--------|------|
| Claude Code | user-scope MCP registry (`claude mcp add --scope user`) | pinned `npx` stdio | Eager `chrome-devtools` comes from the bundled `.mcp.json` (never written to `~/.claude.json` - a duplicate is what causes the "skipped" notes). Step 12 registers ONLY the five opt-in families at user scope, on demand. |
| Codex CLI | `~/.codex/config.toml` | TOML - `[mcp_servers.<name>]` with `command` / `args` | Written only when `~/.codex/config.toml` already exists (Codex is installed). |
| Gemini CLI | `~/.gemini/settings.json` (key `mcpServers`) | JSON - per-server entry plus `"trust": true` to skip prompts | Written only when `~/.gemini/settings.json` already exists. |

The browser servers are local stdio `npx` servers (no API key needed), unlike the
`odoo-semantic` HTTP server documented above - so this wiring is independent of the
`/odoo-semantic-mcp:connect` flow.

---

## OpenAI Codex CLI

Docs: <https://developers.openai.com/codex/mcp>

Edit `~/.codex/config.toml` (the `codex mcp add` CLI does not support a `--header` flag - you must edit the TOML directly):
```toml
[mcp_servers.odoo-semantic]
url = "<MCP_URL>"
http_headers = { "X-API-Key" = "<API_KEY>" }
```

Restart Codex. Verify: `codex mcp list`.

**Pitfall:** the key must be `http_headers` (snake_case, plural). Writing `headers = ...` causes Codex to silently ignore it and send no auth header, resulting in a 401 from the MCP server.

**Timeout (recommended):** the server already bounds each query and rejects fast under
load; as a defensive backstop against a transport-level stall, set Codex's per-server
tool-call timeout (Codex uses seconds, not ms - add `tool_timeout_sec = 90`
to the `[mcp_servers.odoo-semantic]` block; confirm the exact key against the Codex
docs linked above, as Codex's config schema differs from Claude Code's).

### Auto-trust: skip permission prompts
<a id="codex-cli-auto-trust"></a>

> **Trade-off**: Codex CLI has no per-server pre-approval mechanism. Each tool will prompt for confirmation on first use. This is a limitation of the Codex CLI, not the server. The only workaround is setting `approval_policy = "never"` in config - but that affects all tools, which is not recommended.

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
      "timeout": 90000
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

Command Palette (`Ctrl/Cmd+Shift+P`) → **`MCP: Open User Configuration`** - opens `mcp.json`:
```json
{
  "servers": {
    "odoo-semantic": {
      "type": "http",
      "url": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" },
      "timeout": 90000
    }
  }
}
```

Copy-ready snippet (uses `${input:odoo-api-key}` for secure key prompting): [`snippets/vscode-mcp.json`](../snippets/vscode-mcp.json)

Click the **Start** codelens that appears on the server block, or reload the window.

**Pitfall:** the top-level key is `servers` (not `mcpServers` as in Claude/Gemini/Antigravity). `type` must be exactly `"http"` (not `"streamable-http"`). Do not put MCP servers into `settings.json` - use the separate `mcp.json` file.

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

IDE → **Manage MCP Servers → View raw config** - or edit `~/.gemini/antigravity/mcp_config.json` directly:
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "serverUrl": "<MCP_URL>",
      "headers": { "X-API-Key": "<API_KEY>" },
      "timeout": 90000
    }
  }
}
```

Copy-ready snippet: [`snippets/antigravity-mcp.json`](../snippets/antigravity-mcp.json)

Save → click **Refresh** in the MCP panel.

**Pitfall:** the property must be `serverUrl` (camelCase, not `url` or `httpUrl`). The file lives under `~/.gemini/antigravity/` - it shares a path prefix with Gemini CLI but has a different schema.

### Auto-trust: skip permission prompts
<a id="antigravity-auto-trust"></a>

After adding the server: go to **... → MCP Servers** → find `odoo-semantic` → add the allow-list pattern `mcp(odoo-semantic.*)` to pre-approve all tools.

> Antigravity has only a global config, no project-level config. The API key is stored in plaintext in `~/.gemini/antigravity/mcp_config.json` - ensure the file has `600` permissions.

---

## Windsurf

Docs: <https://docs.windsurf.com/windsurf/mcp>

Edit `~/.windsurf/mcp_config.json` (global) or `.windsurf/mcp_config.json` (project):
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "serverUrl": "https://odoo-semantic.viindoo.com/mcp",
      "headers": { "X-API-Key": "<YOUR_API_KEY>" },
      "timeout": 90000
    }
  }
}
```

Copy-ready snippet: [`snippets/windsurf-mcp.json`](../snippets/windsurf-mcp.json)

Restart Windsurf after saving. Verify: open the MCP panel and confirm the server status shows **Connected**.

**Pitfall:** Windsurf uses `serverUrl` (camelCase) just like Antigravity, not `url`. Using `url` causes the server entry to be silently ignored.

---

## Zed

Docs: <https://zed.dev/docs/assistant/model-context-protocol>

Edit `~/.config/zed/settings.json` and add (or merge) the `context_servers` block:
```json
{
  "context_servers": {
    "odoo-semantic": {
      "url": "https://odoo-semantic.viindoo.com/mcp",
      "headers": { "X-API-Key": "<YOUR_API_KEY>" },
      "timeout": 90000
    }
  }
}
```

Copy-ready snippet: [`snippets/zed-mcp.json`](../snippets/zed-mcp.json)

Reload the window (`Cmd+Shift+P` -> **zed: reload**) after saving.

**Pitfall:** Zed uses the top-level key `context_servers`, not `mcpServers`. Placing the config under `mcpServers` means Zed will not find it.

**Older Zed (pre-native HTTP MCP):** If your Zed version does not yet support native HTTP MCP, use the `mcp-remote` proxy:

```json
{
  "context_servers": {
    "odoo-semantic": {
      "command": {
        "path": "npx",
        "args": [
          "-y",
          "mcp-remote",
          "https://odoo-semantic.viindoo.com/mcp",
          "--header",
          "X-API-Key:<YOUR_API_KEY>"
        ]
      }
    }
  }
}
```

---

## JetBrains Junie

Docs: <https://www.jetbrains.com/help/idea/junie.html>

Create (or edit) `.junie/mcp/mcp.json` in your project root:
```json
{
  "mcpServers": {
    "odoo-semantic": {
      "url": "https://odoo-semantic.viindoo.com/mcp",
      "headers": { "X-API-Key": "<YOUR_API_KEY>" },
      "timeout": 90000
    }
  }
}
```

Copy-ready snippet: [`snippets/junie-mcp.json`](../snippets/junie-mcp.json)

Commit or `.gitignore` the file as appropriate for your team (the key is sensitive - do not commit a real key to version control). Restart the Junie panel after saving.

**Pitfall:** the file must be placed at `.junie/mcp/mcp.json` relative to the project root, not at the IDE-global config level. A file placed elsewhere will not be picked up.

---

## Session Context Setup (v0.5+) - `set_active_version` / `set_active_profile`

The MCP server supports **sticky session context**: run `set_active_version` once and the value is remembered (24h idle TTL). CAUTION: the pin is scoped per `(api_key_id, mcp_session_id)` - i.e. per MCP session, last-write-wins. Two independent sessions never interfere, but multiple actors sharing ONE session (e.g. a client and any process it dispatches) silently overwrite each other - so under any concurrency pass the concrete `odoo_version` on every call instead of relying on the pin. Similarly `set_active_profile` pins the tenant profile.

**Recommended startup flow** for any AI client (Claude Code, Codex, Gemini, VS Code, Antigravity):

```
1. list_available_versions()    # see which Odoo versions the server has data for
2. set_active_version("<version>")   # pin the version for this session (24h TTL)
3. list_available_profiles()    # see which tenant profiles exist (optional)
4. set_active_profile("<your profile from step 3>")   # pin tenant profile (optional; do not hardcode - use the profile declared for your instance in $ODOO_AI_HOME/instances.toml, or the one you picked in step 3)
5. <every later tool call still passes odoo_version='<version>' explicitly>   # the pin is a probe, not a default
```

After step 2, pass the concrete pinned version on every call, e.g. `model_inspect(model="sale.order", method="summary", odoo_version='<version>')`. The server also accepts `odoo_version='auto'` to resolve against the sticky pin, but because the pin is per-session and racy when actors share one (above), this plugin's skills and agents always pass the concrete version instead.

> See the [implicit session context docs](https://odoo-semantic.viindoo.com/docs/adr/0029-implicit-session-context) for the TTL behavior and pin-keying details.

---

## MCP Resources (`odoo://` URI scheme, v0.5+)

In addition to the tool calls, the server exposes **9 MCP Resources** addressable via stable URIs - preferred when the caller already knows the entity ID and just wants the canonical record (read-only, bookmark-friendly, no parameters):

| URI template | Returns |
|--------------|---------|
| `odoo://{version}/model/{name}` | Model record (inheritance, field/method counts, modules) |
| `odoo://{version}/field/{model}/{field}` | Field record (type, compute, definition module) |
| `odoo://{version}/method/{model}/{method}` | Method record (override chain, super_ratio) |
| `odoo://{version}/module/{name}` | Module record (manifest, defines/extends counts) |
| `odoo://{version}/view/{xmlid}` | View record (xpath chain, inherit_id) |
| `odoo://{version}/pattern/{name}` | Pattern catalogue entry (code snippet + gotchas) |
| `odoo://{version}/stylesheet/{module}/{file_path*}` | Stylesheet record (selectors, imports, variables) |
| `odoo://{version}/test/{module}/{class_name}` | Test class record (base chain, setUp fixtures, test methods) |
| `odoo://{version}/testcoverage/{model}` | Test coverage record (static COVERS_* reference edges for a model) |

**Example:**

```
odoo://17.0/model/sale.order
odoo://17.0/field/sale.order/amount_total
odoo://17.0/view/sale.view_order_form
```

Clients that implement the MCP `resources/list` and `resources/read` flows surface these as bookmark-style references. See the [MCP resources URI scheme docs](https://odoo-semantic.viindoo.com/docs/adr/0030-mcp-resources-uri-scheme) for the URI grammar and authorization model (same `X-API-Key` header as tool calls).

---

## Superset Tools Reference

The server exposes **31 tools**: four discriminator-routed supersets
(`model_inspect`, `module_inspect`, `entity_lookup`, `profile_inspect`), eleven base tools,
four session-context tools, two stylesheet tools (`resolve_stylesheet`, `find_style_override`),
four ORM-validation tools, and six test-surface tools (`find_test_examples`, `tests_covering`,
`test_class_inspect`, `test_base_classes`, `test_coverage_audit`, `js_test_inspect`; added
v0.15.0). Use the supersets below for all model / module / entity queries -
each folds several narrower lookups into one discriminator-routed call:

| Superset tool | Use case | Valid `method` values |
|---------------|----------|-----------------------|
| `model_inspect(model, method, ...)` | Model-level inspection: summary, field/method/view inventory | `summary` · `fields` · `methods` · `views` · `field` · `method` |
| `module_inspect(name, method, ...)` | Module-level inventory: manifest, views, OWL, QWeb, JS patches, dependencies | `summary` · `views` · `owl` · `qweb` · `js` · `dependencies` |
| `entity_lookup(kind, ...)` | Single entity drill-down by ID | kind: `field` · `method` · `view` |
| `profile_inspect(profile, method, ...)` | Profile-level introspection: inheritance chain, repos, module inventory | `summary` · `repos` · `modules` |

### ORM-validation tools (server v0.8.0+)

Static checks against the indexed graph - run them before an AI client suggests a domain,
`@api.depends`, or relational field so hallucinated paths/operators are caught up front:

| Tool | Use case |
|------|----------|
| `resolve_orm_chain(model, dotted_path, odoo_version="<version>")` | Walk a dotted field path; return the terminal type or the first broken hop |
| `validate_domain(model, domain, odoo_version="<version>")` | Validate domain field-paths + operators (operators are **version-aware**) |
| `validate_depends(model, method, odoo_version="<version>")` | Validate a compute method's indexed `@api.depends` paths |
| `validate_relation(model, field, target_model, odoo_version="<version>")` | Assert a relational field's comodel matches the expected target |

**Full side-by-side migration guide:** see the server [CHANGELOG](https://odoo-semantic.viindoo.com/changelog).

---

## Verify After Install - Natural-Language Prompts

After adding the server, type one of the prompts below into your AI tool - the agent should automatically invoke the `odoo-semantic` MCP server and call `model_inspect`. If the agent returns a generic textbook description of `sale.order` instead of citing real module names and an `odoo_version` from the index, the MCP server has not loaded correctly - return to the section for your client.

- *"Using the odoo-semantic tools, show me the full inheritance chain of `sale.order` in Odoo 17.0 - which modules extend it?"*
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
