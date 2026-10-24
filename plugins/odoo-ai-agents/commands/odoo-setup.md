---
name: odoo-setup
argument-hint: "[all|browser|runtime|permissions|auto-mode|listing|instance|venv|refresh|docs-site|author|voice|youtube] [--version X.Y] [--profile P] [--extra SPEC] [--override FILE]"
description: >-
  Sets up browser MCP, permissions and local Odoo instances
---
# /odoo-ai-agents:odoo-setup

Unified, idempotent setup command for the Odoo visual / browser workflow. It drives the numbered
step scripts under `scripts/setup-steps/`, each exposing `describe | check | apply`.

## Argument filter

`$ARGUMENTS` selects which steps run. With no argument (or an unrecognised token), present the
interactive checkbox menu (see "Interactive menu" below).

| Arg            | Runs steps |
|----------------|------------|
| `all`          | Preflight (Gate #1 + Gate #2) then every step in `scripts/setup-steps/` EXCEPT `47-instance-reset`, `60-docs-site`, `65-author-profile`, `70-speech` and `75-youtube` |
| `browser`      | Preflight (Gate #1 soft, Gate #2) then `10-browser-mcp` + `12-browser-mcp-optin` + `20-browser-deps` |
| `runtime`      | Preflight (Gate #1 soft) then `10-browser-mcp` + `12-browser-mcp-optin` (opt-in browser-family wiring only) |
| `permissions`  | `30-permissions` + `32-permissions-state-root` (no preflight needed - config file only) |
| `auto-mode`    | `34-auto-mode` only: `propose` (facts derived from the catalog and the git remotes), show it, then `apply` on consent (no preflight needed - config file only) |
| `listing`      | `35-skill-listing-budget` only (no preflight needed - measures and, with consent, edits the user settings file) |
| `instance`     | Preflight (Gate #1 + Gate #2) then AI-1..AI-6 + `40-instance-profile` + optional `45-venv` + `46-server-wide` + `48-db-local-auth` + `50-instance-spinup`. SKIPS `47` |
| `refresh`      | Preflight (Gate #1 soft) then **Refresh mode** (below) for the declared rows, narrowed by a trailing `--version X.Y` and/or `--profile P`: `45-venv` `record-env` + `suggest`, then AI-6 (`46-server-wide`), then `35-skill-listing-budget` (installed skills change with updates). Declares nothing new. |
| `docs-site`    | `60-docs-site` only (no preflight): `propose`, ask the policy questions, `record` on confirmation - see its step-specific note |
| `author`       | `65-author-profile` only (no preflight): `propose` from the module descriptors, ask for the contact pages, `record` on confirmation - see its step-specific note |
| `venv`         | `45-venv` only, for the declared rows matching `--version` / `--profile` (all rows with a `python` when neither is given): `create-venv --rebuild` in the venv the row already uses, with `--extra SPEC` / `--override FILE` when given and the extras and override the row recorded otherwise, then `record-env`; builds nothing else, asks nothing but the row list - the filter for "requirements changed" or "pin a package" |
| `voice`        | `70-speech` only (no preflight): `propose` the speech providers reachable from this machine, ask for the endpoint, model, key variable NAME and a voice per language, `record` on confirmation - see its step-specific note |
| `youtube`      | `75-youtube` only (no preflight): `propose` what to prepare, ask for the channel label, the OAuth variable NAMES, the default privacy and an optional playlist, `record` on confirmation - see its step-specific note |
| `--reset`      | Runs ONLY `47-instance-reset.sh apply --hard`: backs `instances.toml` up, then clears it. No other steps run. Re-declaring an instance never needs it (see AI-3). |
| (none / unknown) | **Interactive menu** - present AskUserQuestion with multiSelect=true (see below). Do NOT default to `all`. |

For `instance` spin-up, also accept a trailing `--version X.Y` and pass it
through to `50-instance-spinup`.

## The conversation (no-argument mode)

When `$ARGUMENTS` is empty **or** not a valid filter token above, do **NOT** silently run `all`.
Ask what the operator wants to be able to DO, in their own words, with two AskUserQuestion pages
of four options each (`multiSelect: true`). Each option says what it changes on this machine; no
option names a step number, a file or a tool (those belong to the plan it produces).

Page 1 - "What do you want this machine to do?"

```
[ ] Run Odoo locally for development and testing - finds your Odoo checkouts, builds the
    Python environment, lets Odoo reach PostgreSQL, starts an instance. Writes the instance
    registry and a Python environment under your home.

[ ] Rebuild the Python environment of an Odoo you already declared - after a requirements
    change, to pin a package, or when Python is out of range. Rewrites that environment only.

[ ] Take screenshots and record videos of Odoo for documentation and demos - installs the
    browser tooling and allows its tools. Writes browser settings for your AI clients.

[ ] Let the AI do routine Odoo development without asking each time, with protected branches
    kept behind a human - writes the auto-mode rules of your user settings after you review them.
```

Page 2 - "Anything else?"

```
[ ] Publish documentation: the docs site, your company's public contact pages, and the module
    guides - writes the docs-site and vendor profile registries.

[ ] Narrated videos and YouTube publishing - the speech endpoint and voices, and the channels
    videos are published to. Writes two registries; the values go through the plugin's dialog.

[ ] Make the AI see every skill description (when the list is too long) - writes one number to
    your user settings.

[ ] Start the instance registry over - backs it up, then clears it.
```

Map: page 1 = `instance`, `venv`, `browser`, `auto-mode`; page 2 = `docs-site` + `author`,
`voice` + `youtube`, `listing`, `--reset`. Free text in "Other" is mapped to the closest goal and
shown in the plan as "you asked for: <their words> -> <goal>"; never run as `all`. With several
goals ticked, run them in the table's order.

## How this command asks (every question, every goal)

- **Decide from the machine first.** Before asking anything, read what is there: the checkouts
  under `$ODOO_GIT_BASE`, the declared rows of the instance registry, the Python environments
  those rows name, the PostgreSQL that answers, the browser packages, the user settings. A fact
  the machine states is a DECISION the plan shows with its source ("Odoo <X.Y> - from the branch
  of <checkout>"), never a question.
- **Ask only what the machine cannot know**, in the operator's words, one closed question per
  fact, with the outcome in the question ("Which Odoo versions do you work on? I found <X.Y> and
  <X.Z> checkouts") and the vocabulary explained at first use ("a profile is the set of
  repositories your Odoo is built from").
- **One plan, one confirmation.** Everything decided and everything asked becomes one plan:
  what will be written where, what will be installed, what will be started. The operator
  confirms it once (`approve / refine: [feedback] / cancel`); under it nothing asks again,
  except the consent lines below. A `refine` edits the plan and re-presents it.
- **Consent lines - the only questions under an approved plan**: a change to PostgreSQL's
  authentication (`48`), to the permission or auto-mode rules of the user settings (`30`, `32`,
  `34`), or a clone the operator must run themselves. Each is one line that says what changes
  and how it is undone.
- **Never twice.** A fact answered once (a version, a fork account, a repository path) is used
  by every step; a step's own `[Y/n]` is covered by the plan confirmation (the scripts run
  non-interactively).
- **Never a step number, a file name, an exit code or a tool name in a question.** They go in the
  plan and the summary, where a reader can follow them.

## Steps for the AI agent

Let `STEPS_DIR` = the `scripts/setup-steps/` directory inside this plugin
(`${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps` when available, else the
`scripts/setup-steps` dir alongside this command's plugin).

0. **Preflight - two gates before anything else.** Run these BEFORE listing the
   plan or touching any file. They make no changes.

   **Gate #1 - Odoo Semantic MCP connection.** Confirm it is reachable in THIS session.
   - Authoritative check (AI-level): try calling the MCP tool
     `mcp__odoo-semantic__list_available_versions` with no arguments (fallback:
     `mcp__odoo-semantic__cli_help`). This call, not a shell probe, is the source of truth.
     - Responds normally → connected. Continue to Gate #2.
     - Tool is "not found" / unavailable → the server is not loaded in this
       session. **Stop setup and make no changes.** Tell the user: run
       `/odoo-semantic-mcp:connect`, then restart Claude Code and open a NEW
       session (MCP servers do not hot-reload), then re-run
       `/odoo-ai-agents:odoo-setup`.
     - Tool returns a 401 / auth error → Stop and suggest re-running
       `/odoo-semantic-mcp:connect`.
     - Tool returns some other error (server down, self-hosted instance offline)
       → this is a server issue, not a session issue. You MAY continue with a
       clear warning that indexed-codebase grounding will be unavailable until
       the server is back.
   - Shell fallback: `00-osm-gate.sh check` confirms the server is registered in
     `~/.claude.json` and its `/health` endpoint answers. Use it only as a
     secondary signal (e.g. non-interactive runs); the tool call above is authoritative.
   - Filter-aware: for `all` and `instance`, Gate #1 is a HARD block (those
     flows need the backend). For browser-only filters (`browser`, `runtime`,
     `permissions`) it is a SOFT warning - the user may proceed.

   **Gate #2 - Host prerequisites.** Only after Gate #1 passes. Skip this gate
   entirely for `permissions` and `runtime` (they only edit config files).
   - Run `SETUP_FILTER=<filter> "$STEPS_DIR/05-prereq-check.sh" apply` and read the checklist.
   - Every REQUIRED item present: continue without asking - the plan lists what was found.
   - A REQUIRED item missing: stop before the plan with the item in the operator's words and the
     fix the checklist prints ("PostgreSQL is not answering on this machine - start it, or tell
     me where it runs"); when only the instance goal is blocked, offer to go on with the other
     goals and leave the instance for a later run.
   - The two "cannot be auto-detected" boxes of the checklist are not questions: the build
     dependencies are checked by the venv build itself, and a declared venv by the venv gate
     below.
   - **Venv hard-gate.** For every DECLARED source-mode instance in `instances.toml`, the
     checklist verifies the instance's `python` field is populated AND
     `<python> <odoo-bin> --version` actually runs. A source-mode instance with no working venv
     is a REQUIRED item shown missing: the gate reports FAILED with remediation
     (`45-venv.sh create-venv --series <X.Y> --profile <name>`, or point the `python` field at
     an existing venv) and setup does not proceed for that instance. Setting
     `ODOO_AI_ALLOW_NO_VENV=1` downgrades this specific check from FAILED to a printed WARN.

1. **List the plan.** Enumerate the step scripts filtered by `$ARGUMENTS`:
   ```bash
   for s in "$STEPS_DIR"/*.sh; do echo "- $(basename "$s"): $("$s" describe)"; done
   ```
   This is the engine's list; what the OPERATOR sees is the plan of § How this command asks:
   per goal, the decisions with their sources, the questions still open, what will be written,
   installed and started, and which consent lines will come. Map the `$ARGUMENTS` filter to the
   matching scripts (table above) underneath it. Exclude `47-instance-reset` from `all` and `instance`
   plan listings - it runs only via `--reset` - and `60-docs-site`, `65-author-profile`,
   `70-speech` and `75-youtube` - they run only via `docs-site`, `author`, `voice` and `youtube`.

2. **Instance cluster - OSM-grounded propose-then-confirm (AI-1 through AI-5).**
   This cluster runs when the filter is `all` or `instance`. It precedes the
   numbered step scripts `40`/`45`/`46`/`48`/`50` and drives them with confirmed data.
   AI-5 and AI-6 are INSIDE this cluster.

   **AI-1 - OSM version + profile probe (CONFIRM #1)**

   Call `mcp__odoo-semantic__list_available_versions` and
   `mcp__odoo-semantic__list_available_profiles` (no arguments). Then DECIDE before asking:
   - **Versions**: `--version` when given; else the series of every Odoo checkout under
     `$ODOO_GIT_BASE` (the odoo-local `series_detect` tool on each) and of every declared row.
     One or more found: they are the decision, shown with their sources. None: ask "Which Odoo
     versions do you work on?" with the index's list to pick from.
   - **Profile** (explain it once: the set of repositories your Odoo is built from): `--profile`
     when given; else the index profile whose repositories match the checkouts found (their
     `origin_url` through `repo_facts`); exactly one match is the decision; several or none: ask
     which, offering the matches first.
   The decisions and any answer are **CONFIRM #1** - a line of the plan, not a question of their
   own.

   **OSM unavailable - Degraded Case 2:** If `list_available_versions` or
   `list_available_profiles` fails or is unreachable, do NOT abort. Warn the user that there is no
   OSM grounding, ask for Odoo version(s), profile name and the repo list (SSH URL, branch, role),
   and continue to AI-3 directly (skip AI-2). This is the **user-declared path** - label all output
   "no OSM grounding - user-declared".

   **AI-2 - OSM repo set (CONFIRM #2)**

   For each version confirmed in AI-1, call:
   ```
   mcp__odoo-semantic__profile_inspect(method='repos', name=<profile>, odoo_version=<version>)
   ```
   (fall back to `method='summary'` if `repos` is unsupported). OSM returns a
   repo set: SSH URL @ branch, own vs. inherited. Before anything is proposed, confirm each
   repository HAS a branch for the series on its remote: `python3
   "$STEPS_DIR/../lib/remote_branch_facts.py" <url> <branch>` (one probe per repository, the
   clone of a sibling series answers for its origin). A repository whose branch is absent is
   listed in the plan as "<repo>: no <series> branch on its remote - left out" and never
   proposed for a clone; an unreachable remote is listed as unknown and the clone command of
   AI-3 still goes to the operator. Show the set in the plan ("Repositories: ... from the
   index"); a repository the operator wants added is given when they confirm the plan
   (`refine: add <url> <branch> own|inherited`). This is **CONFIRM #2** - part of the plan.

   **AI-3 - Local repo scan + missing repo guidance (CONFIRM #3)**

   Spawn a **read-only HAIKU subagent** to scan local repos and build a
   mapping: each OSM repo (normalized SSH URL + branch) → local absolute path.

   Normalization: strip `git@github.com:` vs `https://github.com/` prefix and
   `.git` suffix → canonical key `github.com/<Org>/<repo>`; match against
   the `origin_url` (odoo-local `repo_facts`) of every local directory under
   `$ODOO_GIT_BASE` (or a set of candidate parent directories the user
   suggests). Branch must also match.

   The HAIKU subagent is **read-only**: it calls `repo_facts` on local
   directories and reads `origin_url` and `branch`; it makes no writes,
   no clones, no edits.

   For each repo in the confirmed set:
   - **MATCHED** → record the local absolute path; show it to the user. After the last repo, run
     `python3 "$STEPS_DIR/../lib/fork_facts.py" --summary --repo <path> [--repo <path> ...]` once over
     every matched repo of role `own` and follow **Fork resolution**; an `inherited` repo gets none.
   - **MISSING** → compose and print for the user (the agent does NOT run it) a clone
     command: git clone with -b BRANCH, --no-single-branch, SSH_URL, into a local
     directory named `odoo<major>` - where BRANCH and SSH_URL come from OSM at runtime
     (`<Org>/<repo>` is the runtime placeholder).
     Do **NOT** auto-clone. Print the command and ask the user to run it first, then
     re-run this step - or confirm they want to skip that repo. Fork resolution runs
     for an `own` repo once it is cloned.

   The addons path order is a rule, shown and not asked: **own repos first → ancestor/inherited
   repos → Odoo core last**; a reorder arrives as a `refine` of the plan. The matched paths and
   the order are **CONFIRM #3** - a block of the plan. Once the plan is approved, call `40 apply`
   with the confirmed spec via env
   `ODOO_AI_PROFILE_SPEC` (a JSON array of instance objects). Step `40` refuses
   to auto-write without this env - never call `40 apply` without it.

   **Running it again is the normal way to change an instance.** A series and profile already
   declared is UPDATED in place by `40 apply`: its addons path follows the plan (a repository
   added, removed or reordered), its port, database and Python stay. The plan says which it is
   ("Instance <X.Y>:<profile>: already declared - addons path will be updated" or
   "- unchanged"); nothing is duplicated and nothing is skipped silently. `--reset` is for
   starting the whole registry over, never for changing one instance.

   **AI-4 - Venv scan (CONFIRM #4)**

   Spawn a **read-only HAIKU subagent** to map each local Python virtual
   environment to its Odoo series. It only scans and reports - it does NOT run `45` or `50`; the
   orchestrator runs those after CONFIRM #4. **Detect the series by RUNNING Odoo, never by a bare
   `import odoo`.**

   Candidate venv locations to scan (check in this order):
   - The `python` field in `$ODOO_AI_HOME/instances.toml` for the matching series
     (if already set from a previous run).
   - `venvs/<series>-<profile>` inside the project's Tier-2 SHARE dir
     (`scripts/lib/resolve_project_dir.sh share`; per-profile venv path
     written by `45 create-venv`).
   - Any path the user already named in this session.

   Two probes (the subagent only reads / runs `--version`, installs nothing). Try Probe 1 first;
   fall back to Probe 2 when the core repo is not available:
   - **Probe 1** - `<venv>/bin/python <core-repo>/odoo-bin --version` (the core repo's
     launcher is `openerp-server` instead on the series whose core package is `openerp/`)
     (`<core-repo>` = the repo with role `core` confirmed in CONFIRM #3 - the
     last entry in the addons_path order own-repos-first -> ancestor -> core-last).
   - **Probe 2** - `<venv>/bin/python -c "import odoo.release; print(odoo.release.version)"`
     - use as fallback when the core repo path is not yet known.

   **"Ambiguous output"** = the probe ran but did not print a recognisable
   version string `X.Y` (exit code != 0, traceback, or non-numeric output).

   Do NOT inspect `import odoo` / `odoo.__file__` / `site-packages/odoo`.

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

   The decision is made from the probes and shown in the plan - **CONFIRM #4**: `MATCHED` =
   reuse that venv (its path in the plan); `MISSING` = build one with the Python the checkout
   recommends and `uv` when installed else `pip` ("Python environment for <X.Y>: will be built
   with Python <version> at <path>, about 5 minutes"); only `UNKNOWN` is a question ("Which of these
   environments runs your Odoo <X.Y>?", or "where is the core checkout?"). The operator changes a
   decision with a `refine`. After approval the orchestrator runs `45-venv.sh create-venv` for the
   series to build, and then, for EVERY series in the confirmed spec - including a series whose
   venv was reused:

   ```
   "$STEPS_DIR/45-venv.sh" record-env --series <X.Y> [--profile <name>]
   ```

   It asks nothing and records only VERIFIED facts (`python`, `odoo_root`,
   `db_run_mode`/`db_container`). Never skip it. A non-zero exit names the fact it could not
   determine - report and continue.

   **AI-5 - DB local auth (CONFIRM #5)**

   For EVERY series in the confirmed spec, run
   `"$STEPS_DIR/48-db-local-auth.sh" check --series <X.Y> [--profile <name>]`.
   Exit `0` → nothing to do. Exit `1` → show the rule `apply` adds to that cluster's `pg_hba.conf`
   (`host all <declared db_user> <discovered-addr>/32 trust`), the container it edits (if any), and
   that `48-db-local-auth.sh revert` undoes it. It changes PostgreSQL config, so it
   is **never** silent: it is a CONSENT LINE under the plan - "To let Odoo reach PostgreSQL I
   will add one line to its access rules (host all <role> <addr>/32 trust) <in container X>; undo
   with 48-db-local-auth.sh revert. Go ahead?" - **CONFIRM #5**; then run `48 apply --series
   <X.Y> [--profile <name>]`. Forward its output verbatim. On a refusal (a `tcp-only`,
   managed or remote cluster) report it to the user as-is and continue; builds on that cluster
   stay refused with `DB_AUTH_DENIED`.

   **AI-6 - Server-wide modules (CONFIRM #6)**

   Never compose `--load`. For EVERY series (and profile) in the confirmed spec, after AI-4 recorded
   `odoo_root`:

   1. **Local evidence.** Run `"$STEPS_DIR/46-server-wide.sh" propose --series <X.Y>
      [--profile <name>]`. Read its facts: `CORE_SERVER_WIDE_MODULES` (applied by the tools,
      never recorded), `SELF_DECLARED_SERVER_WIDE` (addons on the row's addons_path whose own
      code tests their name against `server_wide_modules`), `MANIFEST_HINTS` (addons whose
      manifest summary or description says they load server wide), `CURRENT_SERVER_WIDE_MODULES`
      and `UNDETECTED_CURRENT` (already declared, and which of those nothing re-found - typically
      an operator's own addition: keep it unless the operator drops it), and
      `PROPOSED_SERVER_WIDE_MODULES` with `PROPOSAL_SOURCES` (each module's evidence: code, log,
      manifest, row) - show the operator that source beside each candidate. `CORE_READABLE=0`: fix
      `odoo_root` (AI-4) first.
   2. **Odoo Semantic evidence** (skip on the user-declared path, and say so). Call
      `mcp__odoo-semantic__find_examples(query='server_wide_modules', odoo_version=<X.Y>,
      profile_name=<profile>, limit=20)` and take every module whose code tests ITS OWN name
      against `server_wide_modules`. Such checks usually run at import time in a module's
      `__init__.py`: an empty answer is never evidence of "none" - step 1 is the primary source. Then, for every candidate from any
      source, call `mcp__odoo-semantic__check_module_exists(name=<module>,
      odoo_version=<X.Y>, profile_name=<profile>)` and flag a candidate the profile does not
      contain.
   3. **Probe build (optional - offer it; needs AI-5 done and a runnable venv).** `run_id` =
      `odoo-setup-<X.Y>-<UTC yyyymmddHHMMSS>`. Call the odoo-local tools
      `lease_acquire` (the series and profile, mode `ephemeral`, that run_id, `cwd`, ports 0),
      `instance_build` (op `init`, demo `off`, modules = the candidates so far plus the
      modules the operator deploys on this profile - ask which), then `job_wait` until its
      result is not `timeout`. A module Odoo asked to load server-wide is named in `warnings`;
      re-run step 1 with `--log <the build's log_path>` so it joins the proposal. ALWAYS
      `lease_release` the lease afterwards, whatever the result - this command provisioned it,
      so this command releases it (`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md`
      T3).
   4. **CONFIRM #6.** An EMPTY proposal with nothing currently declared is recorded as a
      confirmed "none" without a question (the plan says "server-wide modules: none found").
      Otherwise the proposal is a block of the plan: each module with its evidence (self-check,
      Odoo Semantic, probe warning, already declared) and the core default (applied
      automatically, not recorded); the operator removes or adds entries by a `refine` - a module
      detection cannot see (one that needs `--load` but leaves no trace in its code or in the
      log, or any module when Odoo Semantic lacks the profile) is theirs to name. Then run
      `"$STEPS_DIR/46-server-wide.sh" record --series <X.Y> [--profile <name>] --modules
      <confirmed,comma,list>` (`--modules ""` records a confirmed "none"). It upserts that one
      key and keeps every other line of the catalog. Never record an unconfirmed list.

   A lease keeps the set it was acquired with: a lease or served instance acquired before the
   record keeps the old set until it is released and acquired again.

   **CONFIRM #7 - which instance starts now**

   One row in the confirmed spec: it starts, the plan says so. Several: the one whose checkout
   is the current working directory when that is one of them; otherwise ask which one starts
   now (never the highest by default). When the chosen series has a profile, pass
   `--profile <name>` to both `45 apply` (if building a venv) and `50 apply`
   so the correct (series, profile) instance block is selected. The OSM profile
   chosen in AI-1 is the `--profile` value.

   The orchestrator then runs `50 apply --version <X.Y> [--profile <name>]`.

3. **For each selected step (non-instance steps), in numeric order:**
   a. Run `"$s" check`. Capture the exit code.
      - Exit `0` → the step is already satisfied. Report
        `✓ <name>: already configured - skipping` and move on.
      - Exit non-zero → the step needs to run. Continue to (b).
   b. The plan the operator approved already says what each step writes (its `describe` line
      and the step-specific notes below, in the operator's words). No per-step `Run <name> now?`.
      Steps `30`, `32` and `34` change the permission or auto-mode rules of the user settings:
      each gets ONE consent line ("I will add these allow rules to your user settings - see them
      above. Go ahead?") before its `apply`; the scripts' own `[Y/n]` runs non-interactively.
   c. Run `"$s" apply` and stream its output to the user.
      - For `35-skill-listing-budget`, the plan carries its `propose` output's `QUESTION`
        rephrased for the operator ("Your skill list is longer than the AI is shown by default, so
        it rarely picks a plugin skill on its own; I can raise that limit in your user settings, at
        about <N> words more per message. Do it?"), and the run is `apply --yes`.
      - For `50-instance-spinup`, pass `--version <X.Y>` if the user confirmed
        one at CONFIRM #7 (or one was discovered in `$ODOO_AI_HOME/instances.toml`).
      - If `apply` exits `2` → it is a refuse-to-corrupt signal (invalid JSON
        target). Surface the stderr verbatim and STOP that step; do not retry,
        do not delete anything.
      - If `apply` exits `1` → report the failure, continue to the next step
        only if the steps are independent (browser-deps failing does not block
        instance-profile).
   d. A consent line declined: skip that step and note the filter that re-runs it.

4. **Final summary**, in the operator's words first: what works now (an instance URL, the
   browsers ready, auto mode on), what was declined and how to come back to it, what failed
   with its one-line cause; then the engine table: each step → `configured` / `skipped (already
   done)` / `skipped (declined)` / `failed`. List any served lease older than 7 days that another
   session holds (`lease_list` scope `all`, `age_s`) with the `lease_gc` remedy. Then remind the user:
   > MCP servers do NOT hot-reload - restart your Claude Code / Codex / Gemini
   > session for the newly wired browser servers and permissions to take effect.

## Refresh mode (`refresh [--version X.Y] [--profile P]`)

Re-derives the facts a DECLARED catalog row carries, without re-declaring it. Use it after a venv,
checkout or addons change, and when a build's `warnings` names a module that must be loaded
server-wide.

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
   Give the operator the lease note from AI-6.

## Fork resolution (steps `34-auto-mode`, `60-docs-site` and AI-3)

Applies only to repos the user pushes to: AI-3 repos of role `own`, the docs repo, the auto-mode
repos. Never to a read-only core or enterprise checkout.

The fork belongs to an ORIGIN (`owner/repo`), never to a clone: ask at most once per origin, and
never once per clone. Read the facts first:

- `34-auto-mode`: `propose` prints a `FORK_QUESTION` only when no fork owner is known on this
  machine. A `fork owner` line means step 34 has its answer: ask nothing.
- `60-docs-site`: `propose` prints `FORK_STATUS` for the docs repo and `FORK_KNOWN_OWNERS` when
  another clone on this machine has a pushed fork.
- AI-3: `fork_facts.py --summary` prints `FORK_KNOWN_OWNERS`, one `FORK_ORIGIN_WITHOUT_FORK` per
  origin none of whose clones has a pushed fork, and `FORK_QUESTION` only when no owner is known.

Resolve:

1. A fork owner is known (`FORK_KNOWN_OWNERS`): ask ONE combined AskUserQuestion (multi-select)
   listing `<owner>/<repo>` for every origin without a pushed fork (step `60`: the docs repo);
   the operator ticks the origins whose fork lives under that owner. With several known owners,
   ask which owner in the same turn.
2. No fork owner is known: ask `FORK_QUESTION` once - which GitHub account holds their fork. The
   answer is the owner for every origin; continue with item 1 using it (step `34` needs nothing more).
3. Never guess or infer an account name; `FORK_UNPUSHED_REMOTES` and `FORK_CANDIDATE_OWNERS` are
   candidates to offer, not answers.
4. A ticked origin whose fork exists but no local remote points at it: add a remote named `fork`
   in each of its clones through `git-toolkit:git-ops`, in one delegation.
5. A ticked origin whose fork does not exist: ask once whether to create the forks. Create them
   only on an explicit yes, through `git-toolkit:git-ops` (it forks and adds the `fork` remote); on
   a no, print the commands for the operator to run.
6. The operator has no GitHub fork workflow: record no fork (`60`: ask which existing remote
   receives their branches; `fork_remote` needs one).
7. Re-run the step's `propose`. A `fork` remote the operator just confirmed is the answer even
   while it is still unpushed: do not ask again, and record it only as the operator confirms it
   (`60`: `fork_remote`; `34` writes a fork owner only once a push to it exists).

## Step-specific notes (what each `apply` does)

- **10-browser-mcp** - wires the browser MCP *registry* for **Codex CLI** and
  **Gemini CLI** only (a `[mcp_servers.*]` table in `$CODEX_CONFIG` and an
  `mcpServers.*` entry with `"trust": true` in `$GEMINI_SETTINGS`). For
  **Claude Code** it writes nothing here: Claude's eager `chrome-devtools` comes
  from the bundled `.mcp.json`, and its five opt-in families are wired by step 12
  - so this step never touches `~/.claude.json`. Packages, pins and server flags come from the
  `scripts/lib/browser_mcp_servers.py` SSOT.
- **12-browser-mcp-optin** - wires the FIVE **opt-in** browser MCP families
  (`chrome-devtools-headed`, `playwright[-headed]`, `pagecast[-headed]`) into
  **Claude Code** at USER scope on demand, idempotent, with the packages, pins and flags
  `scripts/lib/browser_mcp_servers.py` yields. It never touches the eager
  `chrome-devtools`. If the `claude` CLI is not on PATH it prints guidance and does nothing.
  Browser-free host: add `"disabledMcpjsonServers": ["chrome-devtools"]` to the Claude settings and
  do not run step 12.
- **20-browser-deps** - INSTALL-only, never registers or runs anything. Pre-installs the 3 pinned
  browser MCP packages (`scripts/lib/browser_mcp_servers.py` SSOT) on disk via a throwaway
  `npm install --ignore-scripts` (never `npx`/`npm exec`); idempotent. Also runs
  `npx -y playwright install chromium`. For ffmpeg it ONLY prints install guidance - it never
  runs sudo/apt. It never calls `claude mcp add`; registering is exclusively step 10/12's job.
- **30-permissions** - appends browser tool prefixes to `permissions.allow[]`
  in `$CLAUDE_SETTINGS` = `~/.claude/settings.json`. Asks [Y/n] itself.
- **32-permissions-state-root** - appends the 5 narrow state-root
  Bash/Read/Edit rules the planning pipeline needs (resolving and writing
  under `$ODOO_AI_HOME`) to `permissions.allow[]` in the same `$CLAUDE_SETTINGS`.
  Writes `permissions.allow[]` ONLY (never `deny[]`/`ask[]`/
  `additionalDirectories`), and its Write/Edit rules cover ONLY
  `$ODOO_AI_HOME/projects/**` (see `snippets/state-root-resolution.md`), EXCLUDING `bin/`,
  `venvs/`, `node_tools/`, `setup-scripts/`, `runtime/`, and `instances.toml`. Never
  writes the odoo-semantic-mcp permission prefix - that permission's owner is
  `plugins/odoo-semantic-mcp/commands/connect.md` step 5; this step's `check`
  only reports its absence and points there. Honours `ODOO_AI_NO_AUTO_PERMS=1`.
  Grants no Read/Edit rule to an ephemeral state root (under a system temp
  directory or the default root's `scratch/`) and removes its own earlier
  pairs whose root is gone or under a system temp directory.
  Asks [Y/n] itself; after `apply` it prints the exact rules written and
  instructs ONE restart.
- **34-auto-mode** - `propose` derives, from this machine only, the trusted roots (parent of every
  catalog `addons_path` plus the state root's `projects`), the organization (owner of `origin`), the
  fork owner (owner of each other remote the user pushes to, never a fetch-only upstream; one `FORK_QUESTION` only when no clone has a pushed fork - see **Fork resolution**) and the protected branches (the remote's default branch plus
  every `<major>.0` branch); show the proposal, then `apply` on consent. It writes tagged
  `odoo-ai-agents: ` entries into `autoMode.allow`, `autoMode.soft_deny`, `autoMode.environment`
  (each array keeps `"$defaults"` first) and `permissions.ask` push rules for the protected
  branches, in `$CLAUDE_SETTINGS`; never `hard_deny`, never `permissions.allow`. A later `apply`
  prunes this plugin's own tagged entries before writing the current set and never touches yours.
  Honours `ODOO_AI_NO_AUTO_PERMS=1`.
- **35-skill-listing-budget** - measures the session's skill listing (installed plugins enabled
  in the settings files, the user's and the project's skills, `skillOverrides`; Claude Code's
  bundled skills from the CLI's own debug log when a session of this project measured the listing
  after the settings and plugins last changed, else from a cost observed on a named CLI version,
  which the output reports as its `SOURCE`) and decides. Run
  `"$STEPS_DIR/35-skill-listing-budget.sh" propose` and read `ACTION`:
  `fits` / `env-override` / `scope-override` -> report the `NOTE` and move on, nothing to ask.
  `propose` -> put the `QUESTION` line to the user with AskUserQuestion, as given (it states the
  effect and the tokens of context it adds per turn); add `--window <tokens>` to `propose` and `apply` when the
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
  gitignores the project-relative `.odoo-ai/` directory and writes
  `$ODOO_AI_HOME/.gitignore`. Backup + idempotent.
  Also seeds `$ODOO_AI_HOME/i18n.json` (no-clobber) with `{"default_languages":[]}`, the
  default translation-language registry for `odoo-i18n`; languages are added by editing this file.
- **45-venv, `venv` filter (rebuild)** - For each declared row with a `python` that matches
  `--version` / `--profile`, show the row list once and confirm it, then run
  `"$STEPS_DIR/45-venv.sh" create-venv --series <X.Y> [--profile <name>] --rebuild [--extra
  <spec>]... [--override <file>]` followed by `record-env`. The step rebuilds IN PLACE (the row's
  venv, never a new location), refuses while a lease or process uses the venv (it prints them;
  the operator releases or stops them, or says `--force`), keeps the old venv aside until the
  new one runs `odoo-bin --version`, records the extras and the override on the row so the next
  rebuild re-applies them (`--no-recorded` / `--no-override` drop them), and refuses a venv that
  another row also uses unless `--force`. A `SUGGESTED_EXTRA=` line names a lint package an
  addon's tests import; offer it as `--extra`, never add it yourself.
- **45-venv** *(optional, source instances only - offered between 40 and 50)* -
  After `40` declares the profile, offer this flow for the series the user wants to spin up:
  1. Show the supported range and recommended Python:
     `"$STEPS_DIR/45-venv.sh" suggest <series> [--profile <name>]`. The range is read from the
     instance's own Odoo checkout (its `odoo_root`, else the core repo on its addons_path);
     `scripts/lib/odoo-python-matrix.json` answers only when no checkout is readable.
     `create-venv` defaults `--python` to the same recommendation and warns when an explicit
     `--python` lies outside the range.
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
  Never silently pick an incompatible Python. If the user declines, print the suggestion and move
  on. `record-env` runs after CONFIRM #4 (see there); re-run it by hand after any change to the
  venv or the Postgres container.
- **46-server-wide** *(instance sub-step - AI-6, and refresh)* - `propose` prints the
  evidence for a declared row's server-wide modules: Odoo's core default read from the
  checkout, addons whose own code checks their name against `server_wide_modules`, the
  "should be loaded in server wide mode" warnings of any `--log` it is given, and what the row
  already declares; `record --modules <list>` upserts the operator-CONFIRMED list as the row's
  `server_wide_modules` TOML array (other keys, comments and rows untouched; atomic write;
  `--modules ""` = a confirmed none). `check` exits 0 when every declared row carries the key;
  `apply` only prints the proposals and writes nothing - confirmation is the operator's.
- **60-docs-site** *(runs only via `docs-site`; never in `all` or `instance`)* - Ask the operator for
  the path of a local clone of the docs repo. The operator has none: print `git clone <REMOTE>
  <directory beside the operator's other clones>` (`REMOTE` from the repo URL the operator names, or
  from `propose` on another clone), ask the operator to run it and re-run `docs-site`; never clone
  automatically. Then:
  1. Run `"$STEPS_DIR/60-docs-site.sh" propose --repo <path> [--key <id>]` (read-only). Read
     `REMOTE`, `FORK_STATUS`, `FORK_QUESTION`, `FORK_KNOWN_OWNERS`, `FORK_CANDIDATES`, `OTHER_REMOTES`, `SERIES`, `SERIES_<X_Y>_CLONES`,
     `SERIES_<X_Y>_INSTANCES`, `LANGUAGES` (`UNKNOWN` = the repo states none) and `DECLARED`.
     When `FORK_STATUS` is not `fork-remote-pushed`, follow **Fork resolution** before step 2.
  2. Show the facts. Put `FACTS_TO_CONFIRM` and `POLICY_FIELDS_TO_CONFIRM` to the operator with
     AskUserQuestion. Never fill a policy field yourself; leave an unanswered one unset; an empty
     list is a confirmed none. When `DECLARED=1`, offer `show --key <id>` values as defaults.
     Ask whether the docs repo has a forward-port bot; if yes, offer
     `FORWARD_PORT_BRANCH_PATTERN_CANDIDATE` (when non-empty, with its `..._EVIDENCE` branches) as
     the default of `forward_port_branch_pattern` (it must contain `{pr}` and `{series}` only); if
     no, leave it unset. Never record the candidate unconfirmed. Ask which code repositories the
     site documents and record them as `repos` (`owner/repo` or origin URL); never fill it from a guess.
  3. Write the confirmed row as one JSON object to a file under `<state root>/scratch/docs-site-setup/`, then run
     `"$STEPS_DIR/60-docs-site.sh" record --key <id> --from-json <file>` and remove the file after `record`. On a refusal, show stderr,
     correct the answer with the operator and re-run. `record` refuses a row without a `clone` on
     at least one series: offer the `--repo` path. `record` refuses an instance the catalog does not
     declare: route the operator to `/odoo-ai-agents:odoo-setup instance` first, then re-run
     `docs-site`. Never edit `docs-sites.toml` by hand.
  `check` / `show [--key <id>]` read the file; `apply` only advises.
- **65-author-profile** *(runs only via `author`; never in `all` or `instance`)* - The one
  source of every published contact detail. 1. Run `"$STEPS_DIR/65-author-profile.sh" propose
  --addons <the addons directory of the project>` (read-only): it prints `VENDOR`, `WEBSITE`
  and `SUPPORT_EMAIL` read from the module descriptors, and `FACTS_TO_CONFIRM`. 2. Put the
  facts to the operator with AskUserQuestion: confirm vendor and website; ask for the
  pre-sales page (`presales_url`) and the support or ticket page (`support_url`) - web pages,
  `https://`, never an address; the manifest-only `support_email`; `address_policy` (`never`,
  the default, or `image` when the vendor insists on showing an address, rendered as a PNG);
  optionally `font_file`. Never fill a page URL yourself; an unknown one stays unset and the
  page ships without that card. 3. Write the confirmed profile as JSON under
  `<state root>/scratch/author-profile-setup/`, run `"$STEPS_DIR/65-author-profile.sh" record
  --from-json <file>` and remove the file. A refusal names the field; correct it with the
  operator and re-run. `check` / `show` read the profile; `apply` only advises.
- **70-speech** *(runs only via `voice`; never in `all` or `instance`)* - Narration for demo
  videos, vendor-neutral: any endpoint that speaks the OpenAI audio API (`POST
  <base_url>/audio/speech`, optional `GET <base_url>/audio/voices`) for text-to-speech, and
  `POST <base_url>/audio/transcriptions` for the speech-to-text check. 1. Run
  `"$STEPS_DIR/70-speech.sh" propose` (read-only): it lists the provider shapes it knows (a
  gateway, hosted and self-hosted), a gateway the operator exported as `ODOO_AI_SPEECH_BASE_URL`,
  and whether `ffmpeg` has the filters the assembler needs. 2. Ask the operator with
  AskUserQuestion: the TTS `base_url`, `model`, the `auth` mode (`bearer` when the endpoint
  expects a value, `none` for an open self-hosted one), one `voice` per narration language (a
  voice is recorded with the language it is native to; a mismatch is refused), the STT
  `base_url`, `model` and `auth`. When the TTS endpoint lists voices, offer that list. 3. Write
  the confirmed configuration as JSON under `<state root>/scratch/speech-setup/`, run
  `"$STEPS_DIR/70-speech.sh" record --from-json <file>` and remove the file. 4. `auth = bearer`:
  tell the operator to open `/plugin`, choose `odoo-ai-agents`, Configure, and fill in the option
  titled "Speech endpoint key" (the value never goes through the chat), then run
  `/reload-plugins`; then call the odoo-media `media_info` tool (the option shows `true`) and
  `speech_probe` (one short sentence per language, synthesized and transcribed back: `verdict`
  `pass` per language, else the voice or the endpoint is wrong). `check` validates the file only;
  `apply` only advises.
- **75-youtube** *(runs only via `youtube`; never in `all` or `instance`)* - The channels videos
  are published to, by purpose. 1. Run `"$STEPS_DIR/75-youtube.sh" propose` (read-only): it
  prints what the operator prepares on the Google side (a Cloud project with the YouTube Data
  API enabled, a Desktop-type OAuth client and its downloaded client JSON, the consent screen
  External and In production with Branding filled in) and the slots. 2. Ask the operator with
  AskUserQuestion, per channel: the purpose (`docs` for user guides, the docs site and the App
  Store DEMO tab - at least this one; `marketing` for sales and marketing videos; a third purpose
  of theirs), the channel label, the default privacy (`unlisted` until the docs are published),
  an optional playlist id and default language. A purpose without a channel keeps its videos
  local. 3. Per channel, write the confirmed table as JSON under `<state root>/scratch/youtube-setup/`,
  run `"$STEPS_DIR/75-youtube.sh" record --channel <purpose> --from-json <file>` and remove the
  file. 4. Per channel, give the operator the one command THEY run in their own terminal, on a
  machine with a browser: `"$STEPS_DIR/75-youtube.sh" consent --channel <purpose> --client-json
  <downloaded client JSON>` - it completes the consent for the account that owns the channel and
  stores what it obtains in the plugin configuration itself, printing nothing of it; then
  `/reload-plugins`. The agent never runs it. 5. Call the odoo-media `youtube_check` tool
  (channel = purpose, `live` true): the channel title comes back from Google, or the result names
  the option still missing. `check` validates the file only; `apply` only advises.
- **47-instance-reset** *(reset-only - runs ONLY via `--reset`, never via `all` or `instance`)* -
  `--reset` runs `apply --hard`: backs up `instances.toml` to `<path>.bak.<timestamp>` then
  writes an empty registry - what the menu option "Start the instance registry over" promises.
  The script's plain `apply` (hand-run only, no filter reaches it) keeps the rows whose addons
  paths still exist and drops the rest, reformatting any dotted-key block into the
  `[[instance]]` array-of-tables shape. `check` always exits 0.
- **48-db-local-auth** *(instance sub-step - runs between 45 and 50)* - lets Odoo
  reach the declared PostgreSQL role from THIS host, via one
  delimited managed block in that cluster's `pg_hba.conf`:
  `host all <declared db_user> <discovered-addr>/32 trust` - one `/32`, one role.
  Idempotent; backs up before every edit; undone with `48-db-local-auth.sh revert`. REFUSES and
  writes nothing when the address is undiscoverable, the port is published on a non-loopback
  address, or docker access is missing. The arm is decided by where the SERVER is, NOT by
  `db_run_mode`: ONE container publishing the declared `db_port` is edited; TWO publishers is
  refused with both named (declare `db_container` to resolve it); a native SERVER (no container
  publishes that port) gets printed instructions instead; a `tcp-only`, managed or remote cluster
  is refused - AI-5 owns how that refusal is reported.
- **50-instance-spinup** - before launching anything, runs a **fail-loud
  preflight**: (a) `odoo-bin --version` runs under the instance's Python, then
  (b) Odoo's OWN connection through the instance's `python`; `pg_isready` is only a note and never
  makes the launch green. On a refused connection it prints the refusal and
  launches NOTHING. On pass: generates a temp `odoo.conf`, launches Odoo
  (`odoo-bin --dev=all` or `docker compose up -d`), polls the instance's start page
  until it answers HTTP 200, prints the URL. The series comes from CONFIRM #7 (never silently
  defaulted). The Python interpreter comes from the instance `python` field /
  `$ODOO_PYTHON` / `python3`.

## Hard rules

- **Two different Claude files, never crossed.** `~/.claude.json` is the MCP
  server *registry* (step 10 never writes there). `$CLAUDE_SETTINGS`
  (`~/.claude/settings.json`) holds *permissions* - steps 30 and 32 write there. Do not edit
  either file by hand with `Edit`/`Write`.
- **Never sudo silently.** ffmpeg, system packages and a native SERVER's
  `pg_hba.conf` are only *advised*; the user runs any privileged change themselves.
- **Idempotent.** Always run a step's `check` before its `apply`. Re-running
  the whole command must be a no-op when everything is already configured, and re-running a
  goal with a changed answer updates what that answer owns (an instance's addons path, a venv's
  packages, a channel's privacy) - never a second copy, never a silent skip.
- **Spawn a HAIKU subagent ONLY for read-only local filesystem scans** (repo →
  local path mapping in AI-3, venv → series mapping in AI-4). Every file
  mutation goes through the deterministic `*.sh` step scripts (40/45/46/47/48/50/60),
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
  to `~/.claude.json`.

## See also

- `/odoo-semantic-mcp:connect` - connects the Odoo Semantic MCP server.
- `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` - the rung order for the Odoo series,
  OSM profile, addons scope and instance target; the `[[instance]]` entries this command writes are
  its rung 2.
