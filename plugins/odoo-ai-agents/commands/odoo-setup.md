---
name: odoo-setup
argument-hint: "[all|browser|runtime|permissions|auto-mode|listing|instance|venv|refresh|docs-site|author|voice|youtube] [--version X.Y] [--profile P] [--extra SPEC] [--override FILE]"
description: >-
  Sets up browser MCP, permissions and local Odoo instances
---
# /odoo-ai-agents:odoo-setup

Unified, idempotent setup command for the Odoo visual / browser workflow. It drives the numbered
step scripts under `scripts/setup-steps/`, each exposing `describe | check | apply`. Detail lives in
`${CLAUDE_PLUGIN_ROOT}/commands/references/odoo-setup/`: `preflight.md`, `instance-cluster.md`,
`steps-core.md`, `steps-publishing.md` (read the one for the goal in hand, once, before its first step).
`STEPS_DIR` = `${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps`.

## Hard rules

- **Two different Claude files, never crossed.** `~/.claude.json` is the MCP server *registry* (step 10 never
  writes there). `$CLAUDE_SETTINGS` (`~/.claude/settings.json`) holds *permissions* - steps 30 and 32 write
  there. Do not edit either file by hand with `Edit`/`Write`.
- **Never sudo silently.** ffmpeg, system packages and a native SERVER's `pg_hba.conf` are only *advised*; the
  user runs any privileged change themselves.
- **Idempotent.** Always run a step's `check` before its `apply`. Re-running the whole command is a no-op when
  everything is configured, and re-running a goal with a changed answer updates what that answer owns (an
  instance's addons path, a venv's packages, a channel's privacy) - never a second copy, never a silent skip.
- **Spawn a HAIKU subagent ONLY for read-only local filesystem scans** (repo -> local path mapping in AI-3,
  venv -> series mapping in AI-4). Every file mutation goes through the deterministic `*.sh` step scripts
  (40/45/46/47/48/50/60), NEVER through a subagent. The HAIKU subagent reads; the shell scripts write.
- If a step script reports the shared lib missing (`scripts/lib/config_merge.py`, `discover_odoo.sh`, or
  `instances_io.py`), the plugin is partially installed: tell the user to reinstall `odoo-ai-agents@viindoo-plugins`
  fully, restart the session and re-run; never hand-write the browser MCP or permission config in its place. If the
  plugin is installed, do not add the browser servers by hand to `~/.claude.json`. The preflight scripts
  (`00-osm-gate.sh`, `05-prereq-check.sh`) are detect-only; the Gate #1 tool call stays authoritative without
  `00-osm-gate.sh`.

## Argument filter

`$ARGUMENTS` selects which steps run. With no argument (or an unrecognised token), run the conversation below.

| Arg | Runs steps |
|---|---|
| `all` | Preflight (Gate #1 + Gate #2) then every step in `scripts/setup-steps/` EXCEPT `47-instance-reset`, `60-docs-site`, `65-author-profile`, `70-speech` and `75-youtube` |
| `browser` | Preflight (Gate #1 soft, Gate #2) then `10-browser-mcp` + `12-browser-mcp-optin` + `20-browser-deps` |
| `runtime` | Preflight (Gate #1 soft) then `10-browser-mcp` + `12-browser-mcp-optin` (opt-in browser-family wiring only) |
| `permissions` | `30-permissions` + `32-permissions-state-root` (no preflight - config file only) |
| `auto-mode` | `34-auto-mode` only: `propose` (facts from the catalog and the git remotes), show it, `apply` on consent (no preflight) |
| `listing` | `35-skill-listing-budget` only (no preflight - measures and, with consent, edits the user settings file) |
| `instance` | Preflight (Gate #1 + Gate #2) then AI-1..AI-6 + `40-instance-profile` + optional `45-venv` + `46-server-wide` + `48-db-local-auth` + `50-instance-spinup`. SKIPS `47` |
| `refresh` | Preflight (Gate #1 soft) then Refresh mode (`instance-cluster.md` § Refresh mode) for the declared rows, narrowed by a trailing `--version X.Y` and/or `--profile P`: `45-venv` `record-env` + `suggest`, then AI-6 (`46-server-wide`), then `35-skill-listing-budget`. Declares nothing new. |
| `docs-site` | `60-docs-site` only (no preflight): `propose`, ask the policy questions, `record` on confirmation |
| `author` | `65-author-profile` only (no preflight): `propose` from the module descriptors, ask for the contact pages, `record` on confirmation |
| `venv` | `45-venv` only, for the declared rows matching `--version` / `--profile` (all rows with a `python` when neither is given): `create-venv --rebuild` in the venv the row already uses, with `--extra SPEC` / `--override FILE` when given and the extras and override the row recorded otherwise, then `record-env`; builds nothing else, asks nothing but the row list - the filter for "requirements changed" or "pin a package" |
| `voice` | `70-speech` only (no preflight): `propose` the speech providers reachable from this machine, ask for the endpoint, model, key variable NAME and a voice per language, `record` on confirmation |
| `youtube` | `75-youtube` only (no preflight): `propose` what to prepare, ask for the channel label, the OAuth variable NAMES, the default privacy and an optional playlist, `record` on confirmation |
| `--reset` | Runs ONLY `47-instance-reset.sh apply --hard`: backs `instances.toml` up, then clears it. No other steps run. Re-declaring an instance never needs it. |
| (none / unknown) | The conversation below. Do NOT default to `all`. |

For `instance` spin-up, also accept a trailing `--version X.Y` and pass it through to `50-instance-spinup`.
The step-specific notes of `docs-site`, `author`, `voice`, `youtube` are in `steps-publishing.md`.

## The conversation (no-argument mode)

Never silently run `all`. Ask what the operator wants to be able to DO, in their own words, with two
AskUserQuestion pages of four options each (`multiSelect: true`). Each option says what it changes on this
machine; no option names a step number, a file or a tool (those belong to the plan it produces).

Page 1 - "What do you want this machine to do?"
- Run Odoo locally for development and testing - finds your Odoo checkouts, builds the Python environment, lets
  Odoo reach PostgreSQL, starts an instance. Writes the instance registry and a Python environment under your home.
- Rebuild the Python environment of an Odoo you already declared - after a requirements change, to pin a package,
  or when Python is out of range. Rewrites that environment only.
- Take screenshots and record videos of Odoo for documentation and demos - installs the browser tooling and allows
  its tools. Writes browser settings for your AI clients.
- Let the AI do routine Odoo development without asking each time, with protected branches kept behind a human -
  writes the auto-mode rules of your user settings after you review them.

Page 2 - "Anything else?"
- Publish documentation: the docs site, your company's public contact pages, and the module guides - writes the
  docs-site and vendor profile registries.
- Narrated videos and YouTube publishing - the speech endpoint and voices, and the channels videos are published
  to. Writes two registries; the values go through the plugin's dialog.
- Make the AI see every skill description (when the list is too long) - writes one number to your user settings.
- Start the instance registry over - backs it up, then clears it.

Map: page 1 = `instance`, `venv`, `browser`, `auto-mode`; page 2 = `docs-site` + `author`, `voice` + `youtube`,
`listing`, `--reset`. Free text in "Other" is mapped to the closest goal and shown in the plan as "you asked for:
<their words> -> <goal>"; never run as `all`. With several goals ticked, run them in the table's order.

## How this command asks (every question, every goal)

- **Decide from the machine first.** Before asking anything, read what is there: the checkouts under
  `$ODOO_GIT_BASE`, the declared rows of the instance registry, the Python environments those rows name, the
  PostgreSQL that answers, the browser packages, the user settings. A fact the machine states is a DECISION the
  plan shows with its source ("Odoo <X.Y> - from the branch of <checkout>"), never a question.
- **Review the whole registry, then tell.** Run
  `python3 "$STEPS_DIR/../lib/registry_review.py" review "$ODOO_AI_HOME/instances.toml"` before the plan (every
  goal that touches instances: `instance`, `venv`, `refresh`, `all`). Each `FINDING=` line - two rows sharing one
  venv, a duplicate row, an addons path that is gone, a dead or missing Python, a stale comment - is a line of the
  plan in the operator's words with the fix this run applies (a shared venv is split by the rebuild; a duplicate is
  dropped by `registry_review.py dedupe`, the first row kept) or the one choice left to them. Never work around a
  finding in silence, never fix one the plan did not show.
- **Ask only what the machine cannot know**, in the operator's words, one closed question per fact, with the
  outcome in the question ("Which Odoo versions do you work on? I found <X.Y> and <X.Z> checkouts") and the
  vocabulary explained at first use ("a profile is the set of repositories your Odoo is built from").
- **One plan, one confirmation.** Everything decided and everything asked becomes one plan: what will be written
  where, installed, started. The operator confirms it once (`approve / refine: [feedback] / cancel`); under it
  nothing asks again, except the consent lines. A `refine` edits the plan and re-presents it.
- **Consent lines - the only questions under an approved plan**: a change to PostgreSQL's authentication (`48`), to
  the permission or auto-mode rules of the user settings (`30`, `32`, `34`), or a clone the operator must run
  themselves. Each is one line that says what changes and how it is undone.
- **Never twice.** A fact answered once (a version, a fork account, a repository path) is used by every step; a
  step's own `[Y/n]` is covered by the plan confirmation (the scripts run non-interactively).
- **Never a step number, a file name, an exit code or a tool name in a question.** They go in the plan and the
  summary.
- **Never a fill-in template.** A block of `key = value` lines for the operator to complete is not a question. Each
  fact is ONE closed question with the choices the machine found, or a decision the plan shows; the only free-text
  answers are a URL and a label. Model ids, voice ids, auth modes, slots and ids of things the operator has not
  created yet are derived or deferred, never typed.

## Steps for the AI agent

0. **Preflight - two gates** (`references/odoo-setup/preflight.md`; no changes made, before the plan).
   - **Gate #1 - Odoo Semantic MCP connection**: the tool call `mcp__odoo-semantic__list_available_versions`
     (fallback `cli_help`) is authoritative; `00-osm-gate.sh check` is a secondary signal. Not found: stop, no
     changes, tell the user `/odoo-semantic-mcp:connect`, `/reload-plugins`, re-run. 401: stop, suggest `connect`.
     Other error: continue with a warning. HARD block for `all` and `instance`; SOFT for `browser`, `runtime`,
     `permissions`.
   - **Gate #2 - Host prerequisites** (after Gate #1; skipped for `permissions` and `runtime`):
     `SETUP_FILTER=<filter> "$STEPS_DIR/05-prereq-check.sh" apply`. A REQUIRED item missing stops before the plan,
     in the operator's words; the venv hard-gate (`ODOO_AI_ALLOW_NO_VENV=1` downgrades it to a WARN) is in the file.
1. **List the plan.** `for s in "$STEPS_DIR"/*.sh; do echo "- $(basename "$s"): $("$s" describe)"; done` is the
   engine's list; the operator sees the plan of "How this command asks": per goal the decisions with their
   sources, the open questions, what will be written, installed and started, and the consent lines to come. Map
   the filter to the scripts (table above). Exclude `47-instance-reset` from `all` and `instance` listings, and
   `60-docs-site`, `65-author-profile`, `70-speech`, `75-youtube` - they run only via `docs-site`, `author`,
   `voice`, `youtube`.
2. **Instance cluster** (filter `all` or `instance`; precedes `40`/`45`/`46`/`48`/`50` and drives them with
   confirmed data; `references/odoo-setup/instance-cluster.md`). Each CONFIRM is a block of the one plan:
   AI-1 OSM version + profile probe (#1; OSM down = user-declared path, label output "no OSM grounding -
   user-declared") - AI-2 OSM repo set, remote branch probe (#2) - AI-3 local repo scan by a read-only HAIKU
   subagent, print missing clone commands, fork resolution, addons path order own -> ancestor -> core last (#3), then
   `40 apply` ONLY with `ODOO_AI_PROFILE_SPEC` - AI-4 venv scan by running Odoo, never `import odoo` (#4), build
   with `45-venv.sh create-venv`, then `45-venv.sh record-env` for EVERY series - AI-5 `48-db-local-auth.sh check`
   and the consent line before `apply` (#5) - AI-6 server-wide modules: `46-server-wide.sh propose` / `record`, never
   compose `--load`, never record an unconfirmed list (#6) - CONFIRM #7 which instance starts now (never the
   highest by default), then `50 apply --version <X.Y> [--profile <name>]`.
3. **Each selected non-instance step, in numeric order** (`steps-core.md` § Run loop): `check`; exit 0 = report
   `✓ <name>: already configured - skipping`; else `apply` and stream its output. Steps `30`, `32`, `34` get ONE
   consent line before `apply`; `35-skill-listing-budget` runs `apply --yes` after the operator's yes. `apply`
   exit `2` = refuse-to-corrupt: surface stderr verbatim, STOP that step, no retry, delete nothing; exit `1` =
   report, continue only with independent steps. A declined consent line skips the step and names the filter that
   re-runs it.
4. **Final summary**, in the operator's words first (what works now, what was declined and how to come back, what
   failed with its one-line cause), then the engine table: each step -> `configured` / `skipped (already done)` /
   `skipped (declined)` / `failed`; list served leases older than 7 days that another session holds
   (`lease_list` scope `all`, `age_s`) with the `lease_gc` remedy. Then remind the user:
   > `/reload-plugins` reloads the plugin's own servers (odoo-local, odoo-media) and their options; the browser
   > families step 10 registers in your user configuration and the permission rules take effect in a NEW
   > Claude Code / Codex / Gemini session.

## Step notes (what each `apply` does)

Read the note of a step before running it: `steps-core.md` for `10-browser-mcp`, `12-browser-mcp-optin`,
`20-browser-deps`, `30-permissions`, `32-permissions-state-root`, `34-auto-mode`, `35-skill-listing-budget`,
`40-instance-profile`, `45-venv` (rebuild and create), `46-server-wide`, `47-instance-reset` (only via `--reset`),
`48-db-local-auth`, `50-instance-spinup`; `steps-publishing.md` for `60-docs-site`, `65-author-profile`,
`70-speech`, `75-youtube`. Fork resolution (steps `34-auto-mode`, `60-docs-site` and AI-3): `instance-cluster.md`
§ Fork resolution; refresh mode: `instance-cluster.md` § Refresh mode.

## See also

- `/odoo-semantic-mcp:connect` - connects the Odoo Semantic MCP server.
- `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` - the rung order for the Odoo series, OSM profile,
  addons scope and instance target; the `[[instance]]` entries this command writes are its rung 2.
