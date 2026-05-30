---
name: setup
description: One-shot, idempotent setup for the Odoo visual workflow — wire the 3 browser MCP servers across Claude/Codex/Gemini, install browser dependencies, auto-allow tool permissions, and declare + spin up local Odoo instances
---
# /odoo-semantic-skills:setup

Unified, idempotent, extensible setup command for the Odoo visual / browser
workflow. It drives a registry of numbered step scripts under
`scripts/setup-steps/`, each exposing a `describe | check | apply` contract.
Adding a new capability later is a drop-in: add one more numbered script — you
do NOT edit this command.

What it sets up:
1. **Browser MCP** — registers `chrome-devtools`, `playwright`, `pagecast`
   (local stdio `npx` servers) into Claude Code, Codex CLI and Gemini CLI.
2. **Browser deps** — Node >= 20 check, Playwright Chromium install, ffmpeg check.
3. **Permissions** — auto-allows the browser MCP tools in Claude permissions.
4. **Instance profile** — discovers local Odoo repos, writes `.odoo-ai/instances.toml`.
5. **Instance spin-up** — launches a declared Odoo instance and waits for HTTP 200.

## Argument filter

`$ARGUMENTS` selects which steps run. Default (empty) = `all`.

| Arg            | Runs steps |
|----------------|------------|
| `all` / (none) | Preflight (Gate #1 + Gate #2) then every step in `scripts/setup-steps/` |
| `browser`      | Preflight (Gate #1 soft, Gate #2) then `10-browser-mcp` + `20-browser-deps` |
| `runtime`      | Preflight (Gate #1 soft) then `10-browser-mcp` (cross-runtime wiring only) |
| `permissions`  | `30-permissions` (no preflight needed - config file only) |
| `instance`     | Preflight (Gate #1 + Gate #2) then `40-instance-profile` + optional `45-venv` + `50-instance-spinup` |

Parse `$ARGUMENTS` (first token). If it is not one of the above, tell the user
the valid filters and stop. For `instance` spin-up, also accept a trailing
`--version X.Y` and pass it through to `50-instance-spinup`.

Preflight (`00-osm-gate` + `05-prereq-check`) always runs first - see Step 0.
`45-venv` is an optional instance sub-step (offered between `40` and `50`).

## Steps for the AI agent

Let `STEPS_DIR` = the `scripts/setup-steps/` directory inside this plugin
(`${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps` when available, else the
`scripts/setup-steps` dir alongside this command's plugin).

0. **Preflight — two gates before anything else.** Run these BEFORE listing the
   plan or touching any file. They make no changes; they only verify the ground
   is ready so setup does not half-configure a broken environment.

   **Gate #1 — Odoo Semantic MCP connection.** The instance steps rely on the
   indexing backend, so confirm it is actually reachable in THIS session.
   - Authoritative check (AI-level): try calling the MCP tool
     `mcp__odoo-semantic__list_available_versions` with no arguments (fallback:
     `mcp__odoo-semantic__cli_help`). Only the AI can see whether the tool is
     loaded in the current session, so this call - not a shell probe - is the
     source of truth.
     - Responds normally → connected. Continue to Gate #2.
     - Tool is "not found" / unavailable → the server is not loaded in this
       session. **Stop setup and make no changes.** Tell the user: run
       `/odoo-semantic-mcp:connect`, then restart Claude Code and open a NEW
       session (MCP servers do not hot-reload), then re-run
       `/odoo-semantic-skills:setup`.
     - Tool returns a 401 / auth error → the API key is likely invalid. Stop and
       suggest re-running `/odoo-semantic-mcp:connect` to re-enter the key.
     - Tool returns some other error (server down, self-hosted instance offline)
       → this is a server issue, not a session issue. You MAY continue with a
       clear warning that indexed-codebase grounding will be unavailable until
       the server is back.
   - Shell fallback: `00-osm-gate.sh check` confirms the server is registered in
     `~/.claude.json` and its `/health` endpoint answers. Use it only as a
     secondary signal (e.g. non-interactive runs); the tool call above is
     authoritative for session-load state. It never prints the API key.
   - Filter-aware: for `all` and `instance`, Gate #1 is a HARD block (those
     flows need the backend). For browser-only filters (`browser`, `runtime`,
     `permissions`) it is a SOFT warning - those steps wire the browser MCP and
     do not use the `odoo-semantic-mcp` server, so the user may proceed.

   **Gate #2 — Host prerequisites.** Only after Gate #1 passes. Skip this gate
   entirely for `permissions` and `runtime` (they only edit config files).
   - Run `SETUP_FILTER=<filter> "$STEPS_DIR/05-prereq-check.sh" apply` and show
     the checklist. It probes (read-only, never sudo) the tools setup cannot
     install for you - Node, Python, a running PostgreSQL, cloned Odoo repos,
     etc. - and lists the items only you can confirm (DB role/password, system
     build deps, an Odoo venv).
   - Then require an explicit choice from the user before continuing:
     - `ready` → all required items are satisfied; proceed.
     - `skip instance` → run only browser/permissions steps; skip `40`, `45`,
       and `50`.
     - `cancel` → stop, make no changes.
   - Any REQUIRED auto-detected item shown as missing (marked `[ -- ]`) must be
     fixed before `ready` - point the user at the suggested fix command.

1. **List the plan.** Enumerate the step scripts and show the user what setup
   will cover, filtered by `$ARGUMENTS`:
   ```bash
   for s in "$STEPS_DIR"/*.sh; do echo "- $(basename "$s"): $("$s" describe)"; done
   ```
   Print this as the plan. Map the `$ARGUMENTS` filter to the matching scripts
   (see the table above).

2. **For each selected step, in numeric order:**
   a. Run `"$s" check`. Capture the exit code.
      - Exit `0` → the step is already satisfied. Report
        `✓ <name>: already configured — skipping` and move on.
      - Exit non-zero → the step needs to run. Continue to (b).
   b. **Present what `apply` will do** (use the `describe` line + the
      step-specific notes below) and ask the user for confirmation, e.g.
      `Run <name> now? [Y/n]`. (Step `30-permissions` asks its own [Y/n] inside
      `apply`; you may still surface a heads-up first.)
   c. On `Y`: run `"$s" apply` and stream its output to the user.
      - For `50-instance-spinup`, pass `--version <X.Y>` if the user gave one
        (or one was discovered in `.odoo-ai/instances.toml`).
      - If `apply` exits `2` → it is a refuse-to-corrupt signal (invalid JSON
        target). Surface the stderr verbatim and STOP that step; do not retry,
        do not delete anything.
      - If `apply` exits `1` → report the failure, continue to the next step
        only if the steps are independent (browser-deps failing does not block
        instance-profile).
   d. On `n`: skip the step and note it can be re-run via the matching filter.

3. **Final summary.** Print a table: each step → `configured` / `skipped
   (already done)` / `skipped (declined)` / `failed`. Then remind the user:
   > MCP servers do NOT hot-reload — restart your Claude Code / Codex / Gemini
   > session for the newly wired browser servers and permissions to take effect.

## Step-specific notes (what each `apply` does)

- **10-browser-mcp** — writes the MCP *registry*: `claude mcp add` (or merges
  into `$CLAUDE_CONFIG` = `~/.claude.json`), a `[mcp_servers.*]` table in
  `$CODEX_CONFIG`, and an `mcpServers.*` entry (with `"trust": true`) in
  `$GEMINI_SETTINGS`. No secrets.
- **20-browser-deps** — runs `npx -y playwright install chromium`. For ffmpeg it
  ONLY prints install guidance for your OS — it never runs sudo/apt for you.
- **30-permissions** — appends browser tool prefixes to `permissions.allow[]`
  in `$CLAUDE_SETTINGS` = `~/.claude/settings.json`. Asks [Y/n] itself.
- **40-instance-profile** — runs the Odoo repo discovery, prints the discovered
  TSV for you to confirm the addons-path ordering, writes
  `.odoo-ai/instances.toml` as `[[instance]]` array-of-tables entries keyed by a
  `series` field (one per Odoo series, each with a distinct `http_port`; NO
  password stored), and gitignores `.odoo-ai/`. If no Odoo repo is found it
  writes nothing and tells the user to clone a repo or set `ODOO_GIT_BASE`.
- **45-venv** *(optional, source instances only — offered between 40 and 50)* —
  each Odoo series supports only certain Python versions, so a source instance
  needs an interpreter whose deps match. After `40` declares the profile, offer
  this flow for the series the user wants to spin up:
  1. Show the recommended Python: `"$STEPS_DIR/45-venv.sh" suggest <series>`.
  2. Then let the user choose:
     - **Reuse an existing venv** — set the `python` field on the matching
       `[[instance]]` in `.odoo-ai/instances.toml`, or export `ODOO_PYTHON`.
       Step 50 prefers the `python` field, then `ODOO_PYTHON`, then `python3`.
     - **Build a new venv** (opt-in; needs system build deps):
       `"$STEPS_DIR/45-venv.sh" create-venv --series <X.Y> --tool uv|pip [--python <VER>]`.
       This creates the venv, installs the series' `requirements.txt`, and records
       the interpreter back onto the instance.
  Never silently pick an incompatible Python. If the user declines, just print
  the suggestion and move on - step 50 will fall back to `python3`.
- **50-instance-spinup** — generates a temp `odoo.conf`, launches Odoo (source
  `odoo-bin --dev=all` or `docker compose up -d`), polls `/web/login` to HTTP
  200, prints the URL. With no `--version` it selects the highest declared
  series. The Python interpreter comes from the instance `python` field /
  `$ODOO_PYTHON` / `python3`. The DB password is read only from
  `$ODOO_PG_PASSWORD`.

## Hard rules

- **Two different Claude files, never crossed.** `$CLAUDE_CONFIG`
  (`~/.claude.json`) is the MCP server *registry* — step 10 writes there.
  `$CLAUDE_SETTINGS` (`~/.claude/settings.json`) holds *permissions* — step 30
  writes there. Do not edit either file by hand with `Edit`/`Write`; the step
  scripts back up, refuse invalid JSON, and stay idempotent.
- **Never echo secrets.** No API keys, no DB passwords in any output. DB
  passwords live in `$ODOO_PG_PASSWORD` / a keychain, never in
  `instances.toml`.
- **Never sudo silently.** ffmpeg and system packages are only *advised*; the
  user runs any privileged install themselves.
- **Idempotent.** Always run a step's `check` before its `apply`. Re-running
  the whole command must be a no-op when everything is already configured.
- **Do not spawn a subagent.** This command runs at depth 0. Use the `Bash`
  tool to invoke the step scripts directly.

## Standalone / fallback

- Preflight scripts (`00-osm-gate.sh`, `05-prereq-check.sh`) are detect-only and
  never change anything; if either is missing the plugin is only partially
  installed (reinstall, see below). The authoritative Gate #1 check is still the
  MCP tool call, so preflight degrades gracefully even without `00-osm-gate.sh`.
- If a step script reports the shared lib is missing
  (`scripts/lib/config_merge.py`, `discover_odoo.sh`, or `instances_io.py`), the
  plugin is only partially installed. Tell the user to reinstall
  `odoo-semantic-skills@viindoo-plugins` fully, then point them at the manual
  equivalents:
  - Browser MCP (must match the plugin's `.mcp.json` command + args exactly):
    `claude mcp add --scope user chrome-devtools -- npx -y chrome-devtools-mcp@latest`
    (repeat for `playwright` → `npx -y @playwright/mcp@latest --caps=devtools`,
    `pagecast` → `npx -y @mcpware/pagecast`).
  - Permissions: add `mcp__chrome-devtools`, `mcp__playwright`, `mcp__pagecast`
    to `permissions.allow[]` in `~/.claude/settings.json`.
- If `claude` CLI is absent, step 10 automatically falls back to merging
  `~/.claude.json` directly — no action needed.

## See also

- `/odoo-semantic-mcp:connect` — connect the Odoo Semantic MCP *server*
  (different scope: that is the indexing backend; this command wires the
  *browser* MCP servers + local Odoo instances for the visual workflow).
- `odoo-onboard` skill — writes `.odoo-ai/context.md` (project Odoo version /
  modules / conventions); complementary to this command's `instances.toml`.
