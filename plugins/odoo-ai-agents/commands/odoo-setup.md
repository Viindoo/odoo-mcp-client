---
name: odoo-setup
argument-hint: "[optional: focus area]"
description: One-shot, idempotent setup for the Odoo visual workflow - wire the 3 browser MCP servers across Claude/Codex/Gemini, install browser dependencies, auto-allow tool permissions, and declare + spin up local Odoo instances
---
# /odoo-ai-agents:odoo-setup

Unified, idempotent, extensible setup command for the Odoo visual / browser
workflow. It drives a registry of numbered step scripts under
`scripts/setup-steps/`, each exposing a `describe | check | apply` contract.
Adding a new capability later is a drop-in: add one more numbered script - you
do NOT edit this command.

What it sets up:
1. **Browser MCP** - registers `chrome-devtools`, `playwright`, `pagecast`
   (local stdio `npx` servers) into Claude Code, Codex CLI and Gemini CLI.
2. **Browser deps** - Node >= 20 check, Playwright Chromium install, ffmpeg check.
3. **Permissions** - auto-allows the browser MCP tools in Claude permissions.
4. **Instance profile** - discovers local Odoo repos via OSM-grounded propose-then-confirm,
   writes the machine-global `~/.odoo-ai/instances.toml` (resolvable from any cwd by any agent
   on this host).
5. **Instance spin-up** - launches a declared Odoo instance and waits for HTTP 200.

## Argument filter

`$ARGUMENTS` selects which steps run. **Arguments are optional shortcuts** -
with no argument (or an unrecognised token), the AI agent presents an interactive
checkbox menu so you can pick without memorising filter names (see "Interactive
menu" below).

| Arg            | Runs steps |
|----------------|------------|
| `all`          | Preflight (Gate #1 + Gate #2) then every step in `scripts/setup-steps/` EXCEPT `47-instance-reset` (47 is reset-only, excluded from the all loop) |
| `browser`      | Preflight (Gate #1 soft, Gate #2) then `10-browser-mcp` + `20-browser-deps` |
| `runtime`      | Preflight (Gate #1 soft) then `10-browser-mcp` (cross-runtime wiring only) |
| `permissions`  | `30-permissions` (no preflight needed - config file only) |
| `instance`     | Preflight (Gate #1 + Gate #2) then AI-1..AI-4 + `40-instance-profile` + optional `45-venv` + `50-instance-spinup`. SKIPS `47` (47 is reset-only, excluded from the instance loop) |
| `--reset`      | Runs ONLY `47-instance-reset` (Case 3: backup then clear `instances.toml`). No other steps run. |
| (none / unknown) | **Interactive menu** - present AskUserQuestion with multiSelect=true (see below). Do NOT default to `all`. |

For `instance` spin-up, also accept a trailing `--version X.Y` and pass it
through to `50-instance-spinup`.

## Interactive menu (no-argument mode)

When `$ARGUMENTS` is empty **or** not a valid filter token above, do **NOT**
silently run `all`. Instead present an **AskUserQuestion** with
`multiSelect: true` listing these checkbox options (grouped by user intent, not
internal filter name):

```
Which parts of the Odoo visual workflow would you like to set up?
(You may tick more than one.)

[ ] Browser automation stack - install MCP servers, browser deps, and
    auto-allow tool permissions (runs steps 10, 20, 30)

[ ] Declare + spin up a local Odoo instance - OSM-grounded propose-then-confirm
    flow that writes ~/.odoo-ai/instances.toml and launches an Odoo process
    (runs steps AI-1..AI-4 + 40 + optional 45 + 50)

[ ] Reset instances.toml - backup then clean the instance registry
    (runs step 47 only; equivalent to --reset)
```

Map each ticked option to its corresponding filter/steps and execute them in
numeric order:

| Checkbox ticked | Equivalent filter / steps |
|-----------------|--------------------------|
| Browser automation stack | `browser` - steps 10, 20, 30 |
| Declare + spin up a local Odoo instance | `instance` - AI-1..AI-4 + 40 + optional 45 + 50 |
| Reset instances.toml | `--reset` - step 47 only |

If the user ticks multiple options, run them in the order listed above (browser
steps first, then instance steps, then reset). After collecting selections,
confirm the plan with the user before executing (the normal per-step [Y/n] gates
still apply).

Preflight (`00-osm-gate` + `05-prereq-check`) always runs first - see Step 0.
`45-venv` is an optional instance sub-step (offered between `40` and `50`).
`47-instance-reset` runs ONLY via `--reset` (never in the `all`/`instance` loops).

## Steps for the AI agent

Let `STEPS_DIR` = the `scripts/setup-steps/` directory inside this plugin
(`${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps` when available, else the
`scripts/setup-steps` dir alongside this command's plugin).

0. **Preflight - two gates before anything else.** Run these BEFORE listing the
   plan or touching any file. They make no changes; they only verify the ground
   is ready so setup does not half-configure a broken environment.

   **Gate #1 - Odoo Semantic MCP connection.** Instance steps rely on the
   indexing backend, so confirm it is reachable in THIS session.
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
       `/odoo-ai-agents:odoo-setup`.
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

   **Gate #2 - Host prerequisites.** Only after Gate #1 passes. Skip this gate
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
   (see the table above). Exclude `47-instance-reset` from `all` and `instance`
   plan listings - it runs only via `--reset`.

2. **Instance cluster - OSM-grounded propose-then-confirm (AI-1 through AI-4).**
   This cluster runs when the filter is `all` or `instance`. It precedes the
   numbered step scripts `40`/`45`/`50` and drives them with confirmed data.

   **AI-1 - OSM version + profile probe (CONFIRM #1)**

   Call `mcp__odoo-semantic__list_available_versions` and
   `mcp__odoo-semantic__list_available_profiles` (no arguments). Present the
   results to the user and ask:
   - Which Odoo version(s) / version range do you want to set up? (e.g. `17.0`,
     `16.0-17.0`)
   - Which profile should be used? (pick from the list OSM returned, or type a
     custom name)

   Wait for the user's answer - this is **CONFIRM #1**.

   **OSM unavailable - Degraded Case 2:** If `list_available_versions` or
   `list_available_profiles` fails or is unreachable, do NOT abort. Instead,
   warn the user:
   > "OSM is unavailable - no OSM grounding. You must declare version, profile,
   > and repos manually. The downstream flow is identical; we just cannot
   > cross-check against the indexed source."
   Then ask the user to provide: Odoo version(s), profile name, and the repo
   list (SSH URL, branch, role). Collect these and continue to AI-3 directly
   (skip AI-2). This is the **user-declared path** - label all output clearly
   as "no OSM grounding - user-declared" throughout.

   **AI-2 - OSM repo set (CONFIRM #2)**

   For each version confirmed in AI-1, call:
   ```
   mcp__odoo-semantic__profile_inspect(method='repos', name=<profile>, odoo_version=<version>)
   ```
   (fall back to `method='summary'` if `repos` is unsupported). OSM returns a
   repo set: SSH URL @ branch, own vs. inherited. Present this list to the user
   and ask:
   - Are there repos NOT listed by OSM that you want to include? (provide SSH
     URL, branch, and role - `own` or `inherited`)

   Wait for the user's answer - this is **CONFIRM #2**. Merge any user-added
   repos into the set.

   **AI-3 - Local repo scan + missing repo guidance (CONFIRM #3)**

   Spawn a **read-only HAIKU subagent** to scan local repos and build a
   mapping: each OSM repo (normalized SSH URL + branch) → local absolute path.

   Normalization: strip `git@github.com:` vs `https://github.com/` prefix and
   `.git` suffix → canonical key `github.com/<Org>/<repo>`; match against
   `git remote get-url origin` output of every local directory under
   `$ODOO_GIT_BASE` (or a set of candidate parent directories the user
   suggests). Branch must also match.

   The HAIKU subagent is **read-only**: it runs `git remote get-url` and
   `git rev-parse --abbrev-ref HEAD` in local directories; it makes no writes,
   no clones, no edits.

   For each repo in the confirmed set:
   - **MATCHED** → record the local absolute path; show it to the user.
   - **MISSING** → compose and print for the user (the agent does NOT run these):
     - A clone command: git clone with -b BRANCH, --no-single-branch, SSH_URL,
       into a local directory named `odoo<major>` - where BRANCH and SSH_URL come
       from OSM at runtime (`<Org>/<repo>` is the runtime placeholder).
     - An optional fork-remote step: gh repo fork with --remote and
       --remote-name fork, run inside the cloned directory.
     Do **NOT** auto-clone. Print the commands and ask the user to run them
     first, then re-run this step - or confirm they want to skip that repo.

   Present the matched paths and addons_path ordering to the user. Default
   ordering: **own repos first → ancestor/inherited repos → Odoo core last**
   (Odoo resolves modules FIRST-WINS, so overriding repos must precede core).
   The user may reorder at this point.

   Wait for the user's final confirmation of paths and order - this is
   **CONFIRM #3**. Then call `40 apply` with the confirmed spec via env
   `ODOO_AI_PROFILE_SPEC` (a JSON array of instance objects). Step `40` refuses
   to auto-write without this env - never call `40 apply` without it.

   **AI-4 - Venv scan (CONFIRM #4)**

   Spawn a **read-only HAIKU subagent** to map each local Python virtual
   environment to its Odoo series. The HAIKU subagent only scans and reports
   findings - it does NOT run `45` or `50`; those are run by the orchestrator
   after CONFIRM #4. **Detect the series by RUNNING Odoo, never by a bare
   `import odoo`.**

   Candidate venv locations to scan (check in this order):
   - The `python` field in `~/.odoo-ai/instances.toml` for the matching series
     (if already set from a previous run).
   - `venvs/<series>-<profile>` inside the plugin's `ODOO_AI_DIR` (per-profile
     venv path written by `45 create-venv`).
   - Any path the user already named in this session.

   Two v8-v19-safe probes (the subagent only reads / runs `--version`, installs
   nothing). Try Probe 1 first; fall back to Probe 2 when the core repo is not
   available. They are NOT equivalent - Probe 1 exercises the source checkout
   path while Probe 2 requires a pip-installed package:
   - **Probe 1** - `<venv>/bin/python <core-repo>/odoo-bin --version`
     (`<core-repo>` = the repo with role `core` confirmed in CONFIRM #3 - the
     last entry in the addons_path order own-repos-first -> ancestor -> core-last).
     Authoritative: works for a source checkout that was never pip-installed.
   - **Probe 2** - `<venv>/bin/python -c "import odoo.release; print(odoo.release.version)"`
     - imports the submodule explicitly. Use as fallback when the core repo path
     is not yet known.

   **"Ambiguous output"** = the probe ran but did not print a recognisable
   version string `X.Y` (exit code != 0, traceback, or non-numeric output).

   Do NOT inspect `import odoo` / `odoo.__file__` / `site-packages/odoo`: a
   source-only checkout is not pip-installed (bare import fails even on a
   healthy venv), and Odoo 19 ships `odoo` as a namespace package whose bare
   import exposes no `release`/`__file__` - both make a naive probe report a
   working venv as broken.

   For each series in the confirmed spec:
   - **MATCHED** - the probe prints the expected series: show the venv path.
   - **MISSING** - no venv runs that series: gather `requirements.txt` from
     EVERY repo in that series' confirmed `addons_path` and offer to build one
     via `45-venv.sh create-venv --series <X.Y> --profile <name>` (per-profile
     venv; it verifies all the profile's repos are present and that
     `odoo-bin --version` runs before recording the `python` field).
   - **UNKNOWN** - the probe is inconclusive (ambiguous output, no core repo
     available for Probe 1): do not guess. State exactly what was inconclusive
     and ask the user. Resolution options: (a) if the user confirms the series
     directly, treat as MATCHED and continue; (b) if the user points at the core
     repo path, re-run Probe 1 with that path.

   Wait for the user's choice (reuse existing venv / build new / skip) - this
   is **CONFIRM #4**. The orchestrator then runs `45 apply` for the chosen series.

   **CONFIRM #5 - choose the series and profile to spin up**

   Present the list of series (and profiles, if any were selected in AI-1) in
   the confirmed spec and ask the user which one to launch now. Do not silently
   pick the highest - always ask. When the chosen series has a profile, pass
   `--profile <name>` to both `45 apply` (if building a venv) and `50 apply`
   so the correct (series, profile) instance block is selected. The OSM profile
   chosen in AI-1 IS the `--profile` value passed downstream - both names refer
   to the same instance slot.

   The orchestrator then runs `50 apply --version <X.Y> [--profile <name>]`
   (fail-loud preflight: verify `odoo-bin --version` runs + `pg_isready` before
   launch; see step-specific notes).

3. **For each selected step (non-instance steps), in numeric order:**
   a. Run `"$s" check`. Capture the exit code.
      - Exit `0` → the step is already satisfied. Report
        `✓ <name>: already configured - skipping` and move on.
      - Exit non-zero → the step needs to run. Continue to (b).
   b. **Present what `apply` will do** (use the `describe` line + the
      step-specific notes below) and ask the user for confirmation, e.g.
      `Run <name> now? [Y/n]`. (Step `30-permissions` asks its own [Y/n] inside
      `apply`; you may still surface a heads-up first.)
   c. On `Y`: run `"$s" apply` and stream its output to the user.
      - For `50-instance-spinup`, pass `--version <X.Y>` if the user confirmed
        one at CONFIRM #5 (or one was discovered in `~/.odoo-ai/instances.toml`).
      - If `apply` exits `2` → it is a refuse-to-corrupt signal (invalid JSON
        target). Surface the stderr verbatim and STOP that step; do not retry,
        do not delete anything.
      - If `apply` exits `1` → report the failure, continue to the next step
        only if the steps are independent (browser-deps failing does not block
        instance-profile).
   d. On `n`: skip the step and note it can be re-run via the matching filter.

4. **Final summary.** Print a table: each step → `configured` / `skipped
   (already done)` / `skipped (declined)` / `failed`. Then remind the user:
   > MCP servers do NOT hot-reload - restart your Claude Code / Codex / Gemini
   > session for the newly wired browser servers and permissions to take effect.

## Per-runtime native MCP provisioning

The three browser MCP servers (`chrome-devtools`, `playwright`, `pagecast`) are
provisioned natively by each runtime when the plugin is installed - no manual
step required in the normal flow:

| Runtime | How servers are bundled | Dedup rule |
|---------|------------------------|------------|
| **Claude Code** | Plugin's bundled `.mcp.json` (loaded automatically on install) | Claude deduplicates by command/endpoint: an already-configured server with the same command simply wins; the bundled copy is skipped - this is normal, not an error. No manual step. |
| **Gemini CLI** | Bundled `gemini-extension.json` (installed via `gemini extensions install <your-clone>/plugins/odoo-ai-agents` or `gemini extensions link ...` for live dev). **Note:** Gemini cannot install an extension from a subdirectory of a git repo - the manifest must be at a repo root, so you must install via **local path** after cloning, not directly from a GitHub URL. | Dedup is by server *name*: if the user already has a same-named server in `~/.gemini/settings.json`, that entry wins (no error). The `trust` field is not allowed in the extension manifest. |
| **Codex CLI** | Bundled `.codex-plugin/plugin.json` (installed from a marketplace snapshot). Install flow: `codex plugin marketplace add <marketplace>` then `codex plugin add odoo-ai-agents@<marketplace>`. A Codex marketplace.json publishing this plugin is a separate distribution step (to be published); the manifest ships with the plugin now. | Same dedup-by-name behaviour as Claude. |

> **Fallback:** To wire the browser servers into Codex or Gemini without the plugin
> marketplace, run `/odoo-ai-agents:odoo-setup runtime` - it writes the correct config
> for each runtime idempotently. See [Standalone / fallback](#standalone-fallback) for
> manual equivalents.
>
> **Claude-specific change:** `/odoo-setup` no longer writes the browser servers into
> `~/.claude.json` for Claude Code - Claude is served by the bundled `.mcp.json`, so
> re-running won't recreate the "skipped duplicate" notes there. Step `10-browser-mcp`
> never touches `~/.claude.json` (it wires Codex and Gemini only).

## Step-specific notes (what each `apply` does)

- **10-browser-mcp** - wires the browser MCP *registry* for **Codex CLI** and
  **Gemini CLI** only (a `[mcp_servers.*]` table in `$CODEX_CONFIG` and an
  `mcpServers.*` entry with `"trust": true` in `$GEMINI_SETTINGS`). For
  **Claude Code** it writes nothing: Claude is served by the bundled
  `.mcp.json`, so this step never touches `~/.claude.json`. No secrets.
- **20-browser-deps** - runs `npx -y playwright install chromium`. For ffmpeg it
  ONLY prints install guidance for your OS - it never runs sudo/apt for you.
- **30-permissions** - appends browser tool prefixes to `permissions.allow[]`
  in `$CLAUDE_SETTINGS` = `~/.claude/settings.json`. Asks [Y/n] itself.
- **40-instance-profile** - writes `~/.odoo-ai/instances.toml` as
  `[[instance]]` array-of-tables entries from the confirmed spec passed via
  `ODOO_AI_PROFILE_SPEC` (a JSON array of instance objects). Step `40` does
  NOT auto-discover or auto-write; it refuses `apply` without a confirmed
  `ODOO_AI_PROFILE_SPEC`. The AI agent builds this spec from the OSM-grounded +
  user-confirmed mapping (AI-1..AI-3) and passes it as env before `40 apply`.
  addons_path ordering is own-repos-first → ancestor → core-last; the user may
  reorder at CONFIRM #3. The file is machine-global (resolvable from any cwd);
  a project-local `./.odoo-ai/instances.toml` is honored only as a transitional
  fallback. Step 40 also gitignores the project `.odoo-ai/` and writes a
  defensive `~/.odoo-ai/.gitignore`. Backup + idempotent.
  Also seeds `~/.odoo-ai/i18n.json` (idempotent, no-clobber) with `{"default_languages":["vi_VN"]}` -
  the machine-global default translation-language registry for the odoo-i18n cluster. Edit this file
  to add or remove languages (e.g. `["vi_VN","en_US"]`).
- **45-venv** *(optional, source instances only - offered between 40 and 50)* -
  each Odoo series supports only certain Python versions, so a source instance
  needs a matching interpreter. After `40` declares the profile, offer this flow
  for the series the user wants to spin up:
  1. Show the recommended Python: `"$STEPS_DIR/45-venv.sh" suggest <series>`.
  2. Then let the user choose:
     - **Reuse an existing venv** - set the `python` field on the matching
       `[[instance]]` in `~/.odoo-ai/instances.toml`, or export `ODOO_PYTHON`.
       Step 50 prefers the `python` field, then `ODOO_PYTHON`, then `python3`.
     - **Build a new venv** (opt-in; needs system build deps):
       `"$STEPS_DIR/45-venv.sh" create-venv --series <X.Y> --profile <name> --tool uv|pip [--python <VER>] [--requirements <path>] ...`
       Accepts multiple `--requirements` flags to gather deps from all addon
       repos in the addons_path. This creates the venv under
       `venvs/<series>-<profile>`, installs the deps, verifies all the
       profile's repos are present and that `odoo-bin --version` runs, then
       records the interpreter back onto the instance.
  In both cases, step `45` verifies `odoo-bin --version` runs in the chosen
  interpreter BEFORE writing the `python` field to `instances.toml`. If the
  venv cannot run `odoo-bin --version`, step `45` does NOT record the python
  field and prints an error with guidance.
  Never silently pick an incompatible Python. If the user declines, just print
  the suggestion and move on - step 50 will fall back to `python3`.
- **47-instance-reset** *(reset-only - runs ONLY via `--reset`, never via `all` or `instance`)* -
  `apply`: backs up `instances.toml` to `<path>.bak.<timestamp>` then writes a
  clean replacement. Default mode (`apply`): preserves instances whose local
  paths still exist on disk; removes entries with missing paths and legacy /
  junk records (e.g. version `0.0`, dotted-key format). Hard mode (`apply
  --hard`): wipes all entries unconditionally. `check` always exits 0 (reset
  is always available); it is excluded from the `all`/`instance` loops so it
  never runs silently.
- **50-instance-spinup** - before launching anything, runs a **fail-loud
  preflight**: verifies (a) `odoo-bin --version` runs under the instance's
  Python (confirms the venv is functional and Odoo is reachable) and
  (b) `pg_isready` (or equivalent) confirms PostgreSQL is reachable. If either
  check fails, it prints a clear error with remediation guidance and stops -
  it does NOT launch and then time out polling. On preflight pass: generates a
  temp `odoo.conf`, launches Odoo (`odoo-bin --dev=all` or
  `docker compose up -d`), polls `/web/login` to HTTP 200, prints the URL.
  The series to spin up comes from CONFIRM #5 (never silently defaulted). The
  Python interpreter comes from the instance `python` field / `$ODOO_PYTHON` /
  `python3`. The DB password is read only from `$ODOO_PG_PASSWORD`.

## Hard rules

- **Two different Claude files, never crossed.** `~/.claude.json` is the MCP
  server *registry* - but step 10 deliberately does **not** write there (Claude's
  browser servers come from the plugin's bundled `.mcp.json`).
  `$CLAUDE_SETTINGS` (`~/.claude/settings.json`) holds *permissions* - step 30
  writes there. Do not edit either file by hand with `Edit`/`Write`; the step
  scripts back up, refuse invalid JSON, and stay idempotent.
- **Never echo secrets.** No API keys, no DB passwords in any output. DB
  passwords live in `$ODOO_PG_PASSWORD` / a keychain, never in
  `instances.toml`.
- **Never sudo silently.** ffmpeg and system packages are only *advised*; the
  user runs any privileged install themselves.
- **Idempotent.** Always run a step's `check` before its `apply`. Re-running
  the whole command must be a no-op when everything is already configured.
- **Spawn a HAIKU subagent ONLY for read-only local filesystem scans** (repo →
  local path mapping in AI-3, venv → series mapping in AI-4). Every file
  mutation goes through the deterministic `*.sh` step scripts (40/45/47/50),
  NEVER through a subagent. The HAIKU subagent reads; the shell scripts write.

## Standalone / fallback

- Preflight scripts (`00-osm-gate.sh`, `05-prereq-check.sh`) are detect-only; if
  either is missing the plugin is only partially installed (reinstall, see below).
  The authoritative Gate #1 check is still the MCP tool call, so preflight degrades
  gracefully even without `00-osm-gate.sh`.
- If a step script reports the shared lib is missing
  (`scripts/lib/config_merge.py`, `discover_odoo.sh`, or `instances_io.py`), the
  plugin is only partially installed. Tell the user to reinstall
  `odoo-ai-agents@viindoo-plugins` fully, then point them at the manual
  equivalents:
  - Browser MCP (must match the plugin's `.mcp.json` command + args exactly).
    Each server ships a **headless default** and a **`-headed`** variant; the AI
    picks the headed variant only when the human asks to watch the browser:
    `claude mcp add --scope user chrome-devtools -- npx -y chrome-devtools-mcp@latest --headless --isolated`
    (`chrome-devtools-headed` → drop `--headless`; `playwright` →
    `npx -y @playwright/mcp@latest --caps=devtools --headless --isolated` and
    `playwright-headed` drops `--headless`; `pagecast` →
    `npx -y @mcpware/pagecast --headless` and `pagecast-headed` drops `--headless`).
  - Permissions: add `mcp__chrome-devtools`, `mcp__playwright`, `mcp__pagecast`
    to `permissions.allow[]` in `~/.claude/settings.json`. (With the plugin
    installed, the SessionStart hook `ensure-browser-permissions.sh` adds the
    plugin-namespaced `mcp__plugin_odoo-ai-agents_*` prefixes for you - these
    bare prefixes are only for the standalone, no-plugin case.)
- The manual `claude mcp add` line above is only for using these servers
  **without** the plugin installed. If the plugin is installed, do **not** add
  them to `~/.claude.json` - the bundled `.mcp.json` already provides them, and a
  duplicate entry is exactly what produces the "skipped - same command" notes.

## See also

- `/odoo-semantic-mcp:connect` - connect the Odoo Semantic MCP *server*
  (different scope: that is the indexing backend; this command wires the
  *browser* MCP servers + local Odoo instances for the visual workflow).
- `odoo-onboarding` skill - writes `.odoo-ai/context.md` (project Odoo version /
  modules / conventions); complementary to this command's `instances.toml`.
