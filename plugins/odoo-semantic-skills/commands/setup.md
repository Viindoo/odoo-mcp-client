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
| `all` / (none) | every step in `scripts/setup-steps/` |
| `browser`      | `10-browser-mcp` + `20-browser-deps` |
| `runtime`      | `10-browser-mcp` (cross-runtime wiring only) |
| `permissions`  | `30-permissions` |
| `instance`     | `40-instance-profile` + `50-instance-spinup` |

Parse `$ARGUMENTS` (first token). If it is not one of the above, tell the user
the valid filters and stop. For `instance` spin-up, also accept a trailing
`--version X.Y` and pass it through to `50-instance-spinup`.

## Steps for the AI agent

Let `STEPS_DIR` = the `scripts/setup-steps/` directory inside this plugin
(`${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps` when available, else the
`scripts/setup-steps` dir alongside this command's plugin).

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
  `.odoo-ai/instances.toml` (NO password stored), and gitignores `.odoo-ai/`.
- **50-instance-spinup** — generates a temp `odoo.conf`, launches Odoo (source
  `odoo-bin --dev=all` or `docker compose up -d`), polls `/web/login` to HTTP
  200, prints the URL. The DB password is read only from `$ODOO_PG_PASSWORD`.

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

- If a step script reports the shared lib is missing
  (`scripts/lib/config_merge.py` or `discover_odoo.sh`), the plugin is only
  partially installed. Tell the user to reinstall
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
