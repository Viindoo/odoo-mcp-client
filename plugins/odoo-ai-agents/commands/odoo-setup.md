---
name: odoo-setup
argument-hint: "[all|browser|runtime|permissions|listing|instance|refresh] [--version X.Y] [--profile P]"
description: >-
  Set up browser MCP, permissions and local Odoo instances
---
# /odoo-ai-agents:odoo-setup

Unified, idempotent, extensible setup command for the Odoo visual / browser
workflow. It drives a registry of numbered step scripts under
`scripts/setup-steps/`, each exposing a `describe | check | apply` contract.
Adding a new capability later is a drop-in: add one more numbered script - you
do NOT edit this command.

What it sets up:
1. **Browser MCP** - only ONE family is EAGER: the plugin's bundled `.mcp.json`
   ships the headless `chrome-devtools` (Claude auto-loads it; the Codex/Gemini
   bundle manifests mirror it). The other five families (`chrome-devtools-headed`,
   `playwright[-headed]`, `pagecast[-headed]`) are OPT-IN so a plain session does
   not launch browser processes it does not need. This command wires them on
   demand: `10-browser-mcp` (Codex/Gemini config) and `12-browser-mcp-optin`
   (Claude, user scope) register the opt-in families from the pinned SSOT.
2. **Browser deps** - Node >= 20 check; pre-installs the 3 pinned browser MCP
   packages ON DISK (npm cache warm, never launched - disk cost, zero RAM
   cost); Playwright Chromium install; ffmpeg check. This is INSTALL-only and
   strictly separate from step 12's REGISTER: pre-installing here means a
   later real spawn (once step 12 wires it) has no download latency, without
   ever starting a process or paying idle RAM for it.
3. **Permissions** - auto-allows the browser MCP tools in Claude permissions, plus the
   narrow set of state-root Bash/Read/Edit rules the planning pipeline needs.
4. **Instance profile** - discovers local Odoo repos via OSM-grounded propose-then-confirm,
   writes the machine-global `$ODOO_AI_HOME/instances.toml` (resolvable from any cwd by any agent
   on this host; see `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` for the full
   Tier-1/SHARE/ISOLATE convention). Each row also records its operator-confirmed
   `server_wide_modules` (the deployment's `--load` additions; step `46-server-wide`), and
   `refresh` re-derives a declared row's venv facts and server-wide set. A venv's supported Python
   range is read from the row's Odoo checkout (`45-venv`); a checkout that declares Python 2 gets a
   Python 2.7 venv built with `virtualenv`.
5. **DB local auth** - makes a LOCAL cluster accept the declared PostgreSQL role without a stored
   password, so every build can open Odoo's own connection; reverted with `48-db-local-auth.sh revert`.
   Otherwise the only password sources are `ODOO_PG_PASSWORD` and `~/.pgpass`: a tool-launched Odoo
   never reads the operator's `~/.odoorc`.
6. **Instance spin-up** - launches a declared Odoo instance and waits for HTTP 200.
7. **Skill listing budget** - Claude Code shows the model every skill's description only while
   the session's skill listing fits a budget sized to the context window; at the default budget
   on a 200k-token window most plugin skills are listed without their descriptions. Step `35` measures
   the session's listing and, only when it overflows, offers to raise `skillListingBudgetFraction`
   in your USER settings, showing the per-turn context cost first. On large-context models the
   default budget holds everything and the step does nothing.

## Argument filter

`$ARGUMENTS` selects which steps run. **Arguments are optional shortcuts** -
with no argument (or an unrecognised token), the AI agent presents an interactive
checkbox menu so you can pick without memorising filter names (see "Interactive
menu" below).

| Arg            | Runs steps |
|----------------|------------|
| `all`          | Preflight (Gate #1 + Gate #2) then every step in `scripts/setup-steps/` EXCEPT `47-instance-reset` (47 is reset-only, excluded from the all loop) |
| `browser`      | Preflight (Gate #1 soft, Gate #2) then `10-browser-mcp` + `12-browser-mcp-optin` + `20-browser-deps` |
| `runtime`      | Preflight (Gate #1 soft) then `10-browser-mcp` + `12-browser-mcp-optin` (opt-in browser-family wiring only) |
| `permissions`  | `30-permissions` + `32-permissions-state-root` (no preflight needed - config file only) |
| `listing`      | `35-skill-listing-budget` only (no preflight needed - measures and, with consent, edits the user settings file) |
| `instance`     | Preflight (Gate #1 + Gate #2) then AI-1..AI-6 + `40-instance-profile` + optional `45-venv` + `46-server-wide` + `48-db-local-auth` + `50-instance-spinup`. SKIPS `47` (47 is reset-only, excluded from the instance loop) |
| `refresh`      | Preflight (Gate #1 soft) then **Refresh mode** (below) for the declared rows, narrowed by a trailing `--version X.Y` and/or `--profile P`: `45-venv` `record-env` + `suggest`, then AI-6 (`46-server-wide`), then `35-skill-listing-budget` (installed skills change with updates). Declares nothing new. |
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

[ ] Browser automation stack - wire the opt-in browser MCP families, install
    browser deps, and auto-allow tool permissions (runs steps 10, 12, 20, 30)

[ ] Declare + spin up a local Odoo instance - OSM-grounded propose-then-confirm
    flow that writes $ODOO_AI_HOME/instances.toml and launches an Odoo process
    (runs steps AI-1..AI-6 + 40 + optional 45 + 46 + 48 + 50)

[ ] Show every skill description to the model - measure the skill listing and,
    if it overflows, offer to raise its budget (runs step 35; equivalent to listing)

[ ] Refresh declared instances - re-derive each declared row's venv facts
    and confirm its server-wide modules (equivalent to refresh)

[ ] Reset instances.toml - backup then clean the instance registry
    (runs step 47 only; equivalent to --reset)
```

Map each ticked option to its filter in the table above (`browser`, `listing`, `instance`,
`refresh`, `--reset`); with several ticked, run them in that order. Confirm the plan before
executing - the per-step [Y/n] gates still apply.

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
     etc. - and lists the items only you can confirm (build deps, an Odoo venv).
   - Then require an explicit choice from the user before continuing:
     - `ready` → all required items are satisfied; proceed.
     - `skip instance` → run only browser/permissions steps; skip AI-1..AI-6 and
       `40`, `45`, `46`, `48`, `50`. `48` edits a live cluster's `pg_hba.conf`, so it is
       never reached by a run the user asked to skip.
     - `cancel` → stop, make no changes.
   - Any REQUIRED auto-detected item shown as missing (marked `[ -- ]`) must be
     fixed before `ready` - point the user at the suggested fix command.
   - **Venv hard-gate.** For every DECLARED source-mode instance in `instances.toml`, the
     checklist verifies the instance's `python` field is populated AND
     `<python> <odoo-bin> --version` actually runs. A source-mode instance with no working venv
     is a REQUIRED item shown missing: the gate reports FAILED with remediation
     (`45-venv.sh create-venv --series <X.Y> --profile <name>`, or point the `python` field at
     an existing venv) and setup does not proceed for that instance - it never silently carries
     on with a broken interpreter. Setting `ODOO_AI_ALLOW_NO_VENV=1` downgrades this specific
     check from FAILED to a loud WARN (still printed, never silent) for a conscious
     "build the venv later" choice, without blocking the rest of setup.

1. **List the plan.** Enumerate the step scripts and show the user what setup
   will cover, filtered by `$ARGUMENTS`:
   ```bash
   for s in "$STEPS_DIR"/*.sh; do echo "- $(basename "$s"): $("$s" describe)"; done
   ```
   Print this as the plan. Map the `$ARGUMENTS` filter to the matching scripts
   (see the table above). Exclude `47-instance-reset` from `all` and `instance`
   plan listings - it runs only via `--reset`.

2. **Instance cluster - OSM-grounded propose-then-confirm (AI-1 through AI-5).**
   This cluster runs when the filter is `all` or `instance`. It precedes the
   numbered step scripts `40`/`45`/`46`/`48`/`50` and drives them with confirmed data.
   AI-5 and AI-6 are INSIDE this cluster: stopping after AI-4 leaves step `48` unrun and
   every later build refused on authentication.

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
   - The `python` field in `$ODOO_AI_HOME/instances.toml` for the matching series
     (if already set from a previous run).
   - `venvs/<series>-<profile>` inside the project's Tier-2 SHARE dir
     (`scripts/lib/resolve_project_dir.sh share`; per-profile venv path
     written by `45 create-venv`).
   - Any path the user already named in this session.

   Two v8-v19-safe probes (the subagent only reads / runs `--version`, installs
   nothing). Try Probe 1 first; fall back to Probe 2 when the core repo is not
   available. They are NOT equivalent - Probe 1 exercises the source checkout
   path while Probe 2 requires a pip-installed package:
   - **Probe 1** - `<venv>/bin/python <core-repo>/odoo-bin --version` (the core repo's
     launcher is `openerp-server` instead on the series whose core package is `openerp/`)
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
   is **CONFIRM #4**. The orchestrator then runs `45 apply` for the chosen series,
   and then, for EVERY series in the confirmed spec - including a series whose
   venv was reused or skipped:

   ```
   "$STEPS_DIR/45-venv.sh" record-env --series <X.Y> [--profile <name>]
   ```

   It asks nothing and records only VERIFIED facts (`python`, `odoo_root`,
   `db_run_mode`/`db_container`). Never skip it: `create-venv` records those keys
   only for a venv it just built, so a reused venv gets them from nowhere else and
   an `ephemeral` acquire then refuses with `CREATEDB_UNDETERMINABLE` forever. A non-zero exit names
   the fact it could not determine, records no guess - report and continue.

   **AI-5 - DB local auth (CONFIRM #5)**

   For EVERY series in the confirmed spec, run
   `"$STEPS_DIR/48-db-local-auth.sh" check --series <X.Y> [--profile <name>]`.
   Exit `0` → nothing to do. Exit `1` → Odoo cannot authenticate, so no build can
   start: show the rule `apply` adds to that cluster's `pg_hba.conf` (`host all
   <declared db_user> <discovered-addr>/32 trust`), the container it edits (if any), and
   that `48-db-local-auth.sh revert` undoes it. It changes PostgreSQL config, so it
   is **never** silent: wait for **CONFIRM #5**, then run `48 apply --series <X.Y>
   [--profile <name>]`. Forward its output verbatim. On a refusal (a `tcp-only`,
   managed or remote cluster) the alternative it names is `$ODOO_PG_PASSWORD`, read
   from the ENVIRONMENT OF THE PROCESS that runs each step and exported to libpq as
   `PGPASSWORD` for that launch only - stored nowhere, in no conf file. It must
   therefore be exported BEFORE `50 apply`, in the SAME shell that runs it and every
   later build; a value the human exports in their own terminal never reaches yours.
   NEVER ask for it, echo it, or put it on a command line. When you do not control
   the shell that runs `50 apply` - the normal case - name the durable route instead:
   one `${PGPASSFILE:-~/.pgpass}` line for that host/port/user, which libpq resolves
   in every later process with no export at all. Those two are the only password sources: the
   odoo-local tools never let Odoo read the operator's `~/.odoorc`, so a `db_password` there is not
   used - never propose it. Then continue.

   **AI-6 - Server-wide modules (CONFIRM #6)**

   Which addons a site loads server-wide (`--load`) is a deployment fact kept on each catalog
   row as `server_wide_modules`; Odoo's own core default is a source fact the odoo-local tools
   read from the checkout. Every build and serve applies core default + the row's list by
   default, so an agent never composes `--load` - and a module missing from the row is missing
   from every build that does not add it for its own task (the tools' per-call `server_wide`). For EVERY series (and profile) in the confirmed spec, after AI-4 recorded
   `odoo_root`:

   1. **Local evidence.** Run `"$STEPS_DIR/46-server-wide.sh" propose --series <X.Y>
      [--profile <name>]`. Read its facts: `CORE_SERVER_WIDE_MODULES` (applied by the tools,
      never recorded), `SELF_DECLARED_SERVER_WIDE` (addons on the row's addons_path whose own
      code tests their name against `server_wide_modules`), `CURRENT_SERVER_WIDE_MODULES` and
      `UNDETECTED_CURRENT` (already declared, and which of those nothing re-found - typically an
      operator's own addition: keep it unless the operator drops it), and
      `PROPOSED_SERVER_WIDE_MODULES`. `CORE_READABLE=0` means the checkout is not readable:
      fix `odoo_root` (AI-4) first - the tools refuse a declared list whose core default they
      cannot read.
   2. **Odoo Semantic evidence** (skip on the user-declared path, and say so). Call
      `mcp__odoo-semantic__find_examples(query='server_wide_modules', odoo_version=<X.Y>,
      profile_name=<profile>, limit=20)` and take every module whose code tests ITS OWN name
      against `server_wide_modules`. Such checks usually run at import time in a module's
      `__init__.py`, which the index may not cover: an empty answer is normal and never
      evidence of "none" - step 1 is the primary source. Then, for every candidate from any
      source, call `mcp__odoo-semantic__check_module_exists(name=<module>,
      odoo_version=<X.Y>, profile_name=<profile>)` and flag a candidate the profile does not
      contain.
   3. **Probe build (optional - offer it; needs AI-5 done and a runnable venv).** It catches a
      module whose self-check step 1 could not read, from Odoo's own log line. This command is
      the run that owns the probe, so it names the run: `run_id` =
      `odoo-setup-<X.Y>-<UTC yyyymmddHHMMSS>`. Call the odoo-local tools
      `lease_acquire` (the series and profile, mode `ephemeral`, that run_id, `cwd`, ports 0),
      `instance_build` (op `init`, demo `off`, modules = the candidates so far plus the
      modules the operator deploys on this profile - ask which), then `job_wait` until its
      result is not `timeout`. A module Odoo asked to load server-wide is named in `warnings`;
      re-run step 1 with `--log <the build's log_path>` so it joins the proposal. ALWAYS
      `lease_release` the lease afterwards, whatever the result - this command provisioned it,
      so this command releases it (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
      T3). A build applies what the row
      already declares, so a probe reports only what is still missing.
   4. **CONFIRM #6.** Present the proposal with each module's evidence (self-check, Odoo
      Semantic, probe warning, already declared) and the core default (applied automatically,
      not recorded). Ask the operator to confirm, remove entries, and ADD any module detection
      cannot see - one that needs `--load` but leaves no trace in its code or in the log, or any
      module when Odoo Semantic lacks the profile. Wait for the answer, then run
      `"$STEPS_DIR/46-server-wide.sh" record --series <X.Y> [--profile <name>] --modules
      <confirmed,comma,list>` (`--modules ""` records a confirmed "none"). It upserts that one
      key and keeps every other line of the catalog. Never record an unconfirmed list.

   A lease keeps the set it was acquired with: a lease or served instance acquired before the
   record keeps the old set until it is released and acquired again.

   **CONFIRM #7 - choose the series and profile to spin up**

   Present the list of series (and profiles, if any were selected in AI-1) in
   the confirmed spec and ask the user which one to launch now. Do not silently
   pick the highest - always ask. When the chosen series has a profile, pass
   `--profile <name>` to both `45 apply` (if building a venv) and `50 apply`
   so the correct (series, profile) instance block is selected. The OSM profile
   chosen in AI-1 IS the `--profile` value passed downstream - both names refer
   to the same instance slot.

   The orchestrator then runs `50 apply --version <X.Y> [--profile <name>]`
   (fail-loud preflight: verify `odoo-bin --version` runs, then Odoo's OWN
   connection - a green `pg_isready` is only a cheap note and never makes the
   launch green; see step-specific notes).

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
      - For `35-skill-listing-budget`, the question in (b) is its `propose` output's
        `QUESTION`, and the run on `Y` is `apply --yes` (see its step-specific note).
      - For `50-instance-spinup`, pass `--version <X.Y>` if the user confirmed
        one at CONFIRM #7 (or one was discovered in `$ODOO_AI_HOME/instances.toml`).
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

## Refresh mode (`refresh [--version X.Y] [--profile P]`)

Re-derives the facts a DECLARED catalog row carries, without re-declaring it (step `40` only
adds rows and never overwrites one). Use it after a venv, checkout or addons change, and when a
build's `warnings` names a module that must be loaded server-wide.

1. Preflight Gate #1, SOFT: without Odoo Semantic, AI-6 step 2 is skipped with a warning.
2. Read the declared rows with the odoo-local `catalog_read` tool; keep those matching
   `--version` / `--profile` when given (none given = every row). Show the list and confirm it.
3. For each row, run `"$STEPS_DIR/45-venv.sh" record-env --series <X.Y> [--profile <name>]`
   and forward its output: it re-records only verified facts (`python`, `odoo_root`,
   `db_run_mode`/`db_container`) and warns when the venv's Python lies outside the range the
   checkout declares. Then show `"$STEPS_DIR/45-venv.sh" suggest <X.Y> [--profile <name>]`.
   When the venv is outside the range or `record-env` could not verify it, offer
   `45-venv.sh create-venv` (it builds only on the operator's yes).
4. For each row, run AI-6 (the same evidence, optional probe and CONFIRM #6 gate).
5. Run step `35-skill-listing-budget` as described in its step-specific note (an update can
   add skills and tip the listing over its budget).
6. Summarize per row: the venv facts recorded, and `server_wide_modules` before -> after.
   Remind the operator that leases and served instances acquired earlier keep their old set
   until released and acquired again.

## Per-runtime native MCP provisioning

Only the EAGER `chrome-devtools` family is provisioned natively by each runtime
when the plugin is installed - no manual step required for it. The other five
families (`chrome-devtools-headed`, `playwright[-headed]`, `pagecast[-headed]`)
are OPT-IN: wire them on demand with `/odoo-ai-agents:odoo-setup browser` (step
10 for Codex/Gemini, step 12 for Claude at user scope).

| Runtime | How the eager server is bundled | Dedup rule |
|---------|------------------------|------------|
| **Claude Code** | Plugin's bundled `.mcp.json` (loaded automatically on install; eager `chrome-devtools` only) | The bundled copy is started by `scripts/mcp/browser_mcp_launch.py`, so the state-root flag is applied at every start. No manual step beyond re-running setup after an update. |
| **Gemini CLI** | Bundled `gemini-extension.json` (installed via `gemini extensions install <your-clone>/plugins/odoo-ai-agents` or `gemini extensions link ...` for live dev). **Note:** Gemini cannot install an extension from a subdirectory of a git repo - the manifest must be at a repo root, so you must install via **local path** after cloning, not directly from a GitHub URL. | Started through the same `python3` launcher. Dedup is by server *name*: if the user already has a same-named server in `~/.gemini/settings.json`, that entry wins (no error). The `trust` field is not allowed in the extension manifest. |
| **Codex CLI** | Bundled `.codex-plugin/plugin.json` (installed from a marketplace snapshot). Install flow: `codex plugin marketplace add <marketplace>` then `codex plugin add odoo-ai-agents@<marketplace>`. A Codex marketplace.json publishing this plugin is a separate distribution step (to be published); the manifest ships with the plugin now. | The bundled eager entry is a pinned `npx` command without the state-root flag; step 10 registers it with the flag. Dedup is by server name. |

> **Fallback:** To wire the browser servers into Codex or Gemini without the plugin
> marketplace, run `/odoo-ai-agents:odoo-setup runtime` - it writes the correct config
> for each runtime idempotently. See [Standalone / fallback](#standalone-fallback) for
> manual equivalents.
>
> **Claude:** Step `10-browser-mcp` never writes the browser servers into
> `~/.claude.json` - Claude is served by the bundled `.mcp.json`, so re-running produces
> no "skipped duplicate" notes there. It wires Codex and Gemini only.

## Step-specific notes (what each `apply` does)

- **10-browser-mcp** - wires the browser MCP *registry* for **Codex CLI** and
  **Gemini CLI** only (a `[mcp_servers.*]` table in `$CODEX_CONFIG` and an
  `mcpServers.*` entry with `"trust": true` in `$GEMINI_SETTINGS`). For
  **Claude Code** it writes nothing here: Claude's eager `chrome-devtools` comes
  from the bundled `.mcp.json`, and its five opt-in families are wired by step 12
  - so this step never touches `~/.claude.json`. Packages, pins and server flags come from the
  `scripts/lib/browser_mcp_servers.py` SSOT. No secrets.
- **12-browser-mcp-optin** - wires the FIVE **opt-in** browser MCP families
  (`chrome-devtools-headed`, `playwright[-headed]`, `pagecast[-headed]`) into
  **Claude Code** at USER scope on demand, idempotent, with the packages, pins and flags
  `scripts/lib/browser_mcp_servers.py` yields. It never touches the eager
  `chrome-devtools` (the bundled `.mcp.json` owns that) and needs no permission
  change (browser_prefixes.py allow-lists all six families statically). If the
  `claude` CLI is not on PATH it prints guidance and does nothing. **Opt-out for
  a browser-free host:** to also stop the eager `chrome-devtools` from loading,
  add `"disabledMcpjsonServers": ["chrome-devtools"]` to your Claude settings and
  simply do not run step 12.
- **20-browser-deps** - INSTALL-only, never registers or runs anything. Pre-
  installs the 3 pinned browser MCP packages (`scripts/lib/browser_mcp_servers.py`
  SSOT) on
  disk via a throwaway `npm install --ignore-scripts` (never `npx`/`npm exec`,
  which would execute the package) so npm's cache is warm and a later real spawn
  - by step 10/12's registration - has no download latency; idempotent (`npm install --offline --dry-run` detects an
  already-cached package and skips it). Also runs `npx -y playwright install
  chromium`. For ffmpeg it ONLY prints install guidance for your OS - it never
  runs sudo/apt for you. **Install vs register/run:** this step costs disk, never
  RAM, and never calls `claude mcp add` - registering (and thus ever spawning a
  process, which costs RAM only while a session using it is open) is exclusively
  step 10/12's job.
- **30-permissions** - appends browser tool prefixes to `permissions.allow[]`
  in `$CLAUDE_SETTINGS` = `~/.claude/settings.json`. Asks [Y/n] itself.
- **32-permissions-state-root** - appends the 5 narrow state-root
  Bash/Read/Edit rules the planning pipeline needs (resolving and writing
  under `$ODOO_AI_HOME`) to `permissions.allow[]` in the same `$CLAUDE_SETTINGS`.
  Sibling of `30-permissions`, not folded into it - a distinct, narrower
  capability. Writes `permissions.allow[]` ONLY (never `deny[]`/`ask[]`/
  `additionalDirectories`), and its Write/Edit rules cover ONLY
  `$ODOO_AI_HOME/projects/**` - both the plan (SHARE) and the per-worktree
  worklog (ISOLATE) resolve nested under it (see
  `snippets/state-root-resolution.md`), so a separate `worklog/**` rule would
  target a path that never exists - EXCLUDING `bin/`, `venvs/`,
  `node_tools/`, `setup-scripts/`, `runtime/`, and `instances.toml` (a
  `sitecustomize.py` under `venvs/` or an edited `setup-scripts/*.sh` is
  deferred code execution, not scratch data). Never
  writes the odoo-semantic-mcp permission prefix - that permission's owner is
  `plugins/odoo-semantic-mcp/commands/connect.md` step 5; this step's `check`
  only reports its absence and points there. Honours `ODOO_AI_NO_AUTO_PERMS=1`.
  Asks [Y/n] itself; after `apply` it prints the exact rules written and
  instructs ONE restart (permissions are finalized before SessionStart hooks
  run).
- **35-skill-listing-budget** - measures the session's skill listing (installed plugins enabled
  in the settings files, the user's and the project's skills, `skillOverrides`; Claude Code's
  bundled skills from the CLI's own debug log when it holds a measurement, else from the observed
  value `scripts/lib/skill_listing.py` records with its CLI version) and decides. Run
  `"$STEPS_DIR/35-skill-listing-budget.sh" propose` and read `ACTION`:
  `fits` / `env-override` / `scope-override` -> report the `NOTE` and move on, nothing to ask.
  `propose` -> put the `QUESTION` line to the user with AskUserQuestion, as given (it states the
  effect and the per-turn context cost); add `--window <tokens>` to `propose` and `apply` when the
  user runs a model whose context window differs. Only on a yes run
  `"$STEPS_DIR/35-skill-listing-budget.sh" apply --yes`; on a no, run nothing. It writes only
  the USER settings file (`$CLAUDE_SETTINGS`), never a project or local one, never lowers a
  value, and asks for a restart. Honours `ODOO_AI_NO_LISTING_BUDGET=1`.
- **40-instance-profile** - writes `$ODOO_AI_HOME/instances.toml` as
  `[[instance]]` array-of-tables entries from the confirmed spec passed via
  `ODOO_AI_PROFILE_SPEC` (a JSON array of instance objects). Step `40` does
  NOT auto-discover or auto-write; it refuses `apply` without a confirmed
  `ODOO_AI_PROFILE_SPEC`. The AI agent builds this spec from the OSM-grounded +
  user-confirmed mapping (AI-1..AI-3) and passes it as env before `40 apply`.
  addons_path ordering is own-repos-first → ancestor → core-last; the user may
  reorder at CONFIRM #3. The file is machine-global (resolvable from any cwd);
  a project-local `./.odoo-ai/instances.toml` is honored only as a migration
  source, folded into the machine-global catalog automatically. Step 40 also
  gitignores the project-relative `.odoo-ai/` directory (a repo-relative
  gitignore glob, distinct from the machine-global state root - left as-is) and
  writes a defensive
  `$ODOO_AI_HOME/.gitignore`. Backup + idempotent.
  Also seeds `$ODOO_AI_HOME/i18n.json` (idempotent, no-clobber) with `{"default_languages":[]}` -
  empty, so no locale is assumed on the user's behalf - the machine-global default
  translation-language registry for the odoo-i18n cluster. Edit this file
  to add languages (e.g. `["vi_VN","en_US"]`).
- **45-venv** *(optional, source instances only - offered between 40 and 50)* -
  each Odoo series supports only certain Python versions, so a source instance
  needs a matching interpreter. After `40` declares the profile, offer this flow
  for the series the user wants to spin up:
  1. Show the supported range and recommended Python:
     `"$STEPS_DIR/45-venv.sh" suggest <series> [--profile <name>]`. The range is read from the
     instance's own Odoo checkout (its `odoo_root`, else the core repo on its addons_path);
     `scripts/lib/odoo-python-matrix.json` answers only when no checkout is readable, and the
     output says which source answered. `create-venv` defaults `--python` to the same
     recommendation and warns when an explicit `--python` lies outside the range.
  2. Then let the user choose:
     - **Reuse an existing venv** - set the `python` field on the matching
       `[[instance]]` in `$ODOO_AI_HOME/instances.toml`, or export `ODOO_PYTHON`.
     - **Build a new venv** (opt-in; needs system build deps):
       `"$STEPS_DIR/45-venv.sh" create-venv --series <X.Y> --profile <name> --tool uv|pip [--python <VER>] [--requirements <path>] ...`
       Repeat `--requirements` to gather deps from every addon repo in the
       addons_path. It creates the venv under `venvs/<series>-<profile>`, installs
       the deps, verifies the profile's repos are present and that `odoo-bin
       --version` runs, then records `python`, `odoo_root` and the Postgres client
       surface (`db_run_mode`/`db_container`) onto the instance.
  In both cases `45` verifies `odoo-bin --version` runs in the chosen interpreter
  BEFORE writing the `python` field, and records nothing when it does not.
  Never silently pick an incompatible Python. If the user declines, just print
  the suggestion and move on - step 50 will fall back to `python3`.
  `record-env` runs as part of the numbered flow after CONFIRM #4 (see there);
  re-run it by hand after any change to the venv or the Postgres container.
- **46-server-wide** *(instance sub-step - AI-6, and refresh)* - `propose` prints the
  evidence for a declared row's server-wide modules: Odoo's core default read from the
  checkout, addons whose own code checks their name against `server_wide_modules`, the
  "should be loaded in server wide mode" warnings of any `--log` it is given, and what the row
  already declares; `record --modules <list>` upserts the operator-CONFIRMED list as the row's
  `server_wide_modules` TOML array (other keys, comments and rows untouched; atomic write;
  `--modules ""` = a confirmed none). `check` exits 0 when every declared row carries the key;
  `apply` only prints the proposals and writes nothing - confirmation is the operator's.
- **47-instance-reset** *(reset-only - runs ONLY via `--reset`, never via `all` or `instance`)* -
  `apply`: backs up `instances.toml` to `<path>.bak.<timestamp>` then writes a
  clean replacement. Default mode (`apply`): removes entries whose addons paths
  no longer exist; re-parses and reformats any dotted-key block into the
  `[[instance]]` array-of-tables shape (it does NOT drop version-`0.0`/dotted-key
  records - the only filter is path existence). Hard mode (`apply --hard`): wipes all entries
  unconditionally. `check` always exits 0 (reset is always available); it is
  excluded from the `all`/`instance` loops so it never runs silently.
- **48-db-local-auth** *(instance sub-step - runs between 45 and 50)* - lets Odoo
  reach the declared PostgreSQL role from THIS host without a password, via one
  delimited managed block in that cluster's `pg_hba.conf`:
  `host all <declared db_user> <discovered-addr>/32 trust` - one `/32`, one role.
  The address is DISCOVERED per container (a published-port connection arrives
  from the bridge gateway, never loopback). Idempotent; backs up before every edit
  and never overwrites a backup; undone with `48-db-local-auth.sh revert`; never
  reports success without reconnecting. REFUSES and writes nothing when the
  address is undiscoverable, the port is published on a non-loopback address, or
  docker access is missing. Which arm runs is decided by where the SERVER is, NOT by
  `db_run_mode` (that records only whether libpq binaries are on THIS host's PATH):
  ONE container publishing the declared `db_port` takes the container arm and IS
  edited, even on a `db_run_mode=native` host; TWO publishers is refused with both
  named (declare `db_container` to resolve it); a genuinely native SERVER - no
  container publishes that port - gets printed instructions instead; a `tcp-only`,
  managed or remote cluster is refused - AI-5 owns what to do with the alternative
  it names.
- **50-instance-spinup** - before launching anything, runs a **fail-loud
  preflight**: (a) `odoo-bin --version` runs under the instance's Python, then
  (b) Odoo's OWN connection through the instance's `python`. `pg_isready` runs
  first as a cheap note but can never make the launch green - it answers the same
  whatever the credentials are. On a refused connection it prints the refusal and
  launches NOTHING. On pass: generates a temp `odoo.conf`, launches Odoo
  (`odoo-bin --dev=all` or `docker compose up -d`), polls `/web/login` to HTTP
  200, prints the URL. The series comes from CONFIRM #7 (never silently
  defaulted). The Python interpreter comes from the instance `python` field /
  `$ODOO_PYTHON` / `python3`.

## Hard rules

- **Two different Claude files, never crossed.** `~/.claude.json` is the MCP
  server *registry* - but step 10 deliberately does **not** write there (Claude's
  browser servers come from the plugin's bundled `.mcp.json`).
  `$CLAUDE_SETTINGS` (`~/.claude/settings.json`) holds *permissions* - steps 30
  and 32 write there. Do not edit either file by hand with `Edit`/`Write`; the
  step scripts back up, refuse invalid JSON, and stay idempotent.
- **Never echo secrets, and store no DB password anywhere.** Step 48 makes the
  local cluster accept the declared role without one; `$ODOO_PG_PASSWORD` is the
  escape hatch for a cluster that cannot be reconfigured (scope + ordering: AI-5) -
  never `instances.toml`, never a generated conf, never any output.
- **Never sudo silently.** ffmpeg, system packages and a native SERVER's
  `pg_hba.conf` (one no container publishes - step 48 edits no system file and has
  no flag that makes it) are only *advised*; the user runs any privileged change
  themselves.
- **Idempotent.** Always run a step's `check` before its `apply`. Re-running
  the whole command must be a no-op when everything is already configured.
- **Spawn a HAIKU subagent ONLY for read-only local filesystem scans** (repo →
  local path mapping in AI-3, venv → series mapping in AI-4). Every file
  mutation goes through the deterministic `*.sh` step scripts (40/45/46/47/48/50),
  NEVER through a subagent. The HAIKU subagent reads; the shell scripts write.

## Standalone / fallback

- Preflight scripts (`00-osm-gate.sh`, `05-prereq-check.sh`) are detect-only; if
  either is missing the plugin is only partially installed (reinstall, see below).
  The authoritative Gate #1 check is still the MCP tool call, so preflight degrades
  gracefully even without `00-osm-gate.sh`.
- If a step script reports the shared lib is missing
  (`scripts/lib/config_merge.py`, `discover_odoo.sh`, or `instances_io.py`), the
  plugin is only partially installed and no step can run without it. Tell the user
  to reinstall `odoo-ai-agents@viindoo-plugins` fully, restart the session, and
  re-run this command; do not hand-write the browser MCP or permission config in
  its place.
- If the plugin is installed, do **not** add the browser servers by hand
  to `~/.claude.json` - the bundled `.mcp.json` already provides them, and a
  duplicate entry is exactly what produces the "skipped - same command" notes.

## See also

- `/odoo-semantic-mcp:connect` - connect the Odoo Semantic MCP *server*
  (different scope: that is the indexing backend; this command wires the
  *browser* MCP servers + local Odoo instances for the visual workflow).
- `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` - the rung order every skill
  works to acquire the Odoo series, OSM profile, addons scope and instance target. The
  `[[instance]]` entries this command writes to `instances.toml` are that ladder's rung 2, so
  declaring an instance here is what lets later skills resolve those facts without asking.
