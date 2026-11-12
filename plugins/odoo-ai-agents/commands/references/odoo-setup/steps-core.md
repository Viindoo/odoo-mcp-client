# Run loop, final summary and step notes (browser, permissions, auto mode, listing, instance steps)

Contents: Run loop and final summary - Step notes: 10, 12, 20, 30, 32, 34, 35, 40, 45 (rebuild and
create), 46, 47, 48, 50. Publishing steps (60, 65, 70, 75) are in `steps-publishing.md`.

## Run loop and final summary

**For each selected step (non-instance steps), in numeric order:**
a. Run `"$s" check`. Capture the exit code.
   - Exit `0` → the step is already satisfied. Report
     `✓ <name>: already configured - skipping` and move on.
   - Exit non-zero → the step needs to run. Continue to (b).
b. The plan the operator approved already says what each step writes (its `describe` line
   and the notes of this file and of `steps-publishing.md`, in the operator's words). No per-step `Run <name> now?`.
   Steps `30`, `32` and `34` change the permission or auto-mode rules of the user settings:
   each gets ONE consent line ("I will add these allow rules to your user settings - see them
   above. Go ahead?") before its `apply`; the scripts' own `[Y/n]` runs non-interactively.
c. Run `"$s" apply` and stream its output to the user.
   - For `35-skill-listing-budget`, the plan carries its `propose` output's `QUESTION`
     rephrased for the operator ("Your skill list is longer than the AI is shown by default, so
     it rarely picks a plugin skill on its own; I can raise that limit in your user settings, at
     about <N> words more per message. Do it?"), and the run is `apply --yes`.
   - For `36-claude-tmpdir`, the plan carries its `propose` output's `QUESTION` in the
     operator's words, and the run is `apply --yes`.
   - For `50-instance-spinup`, pass `--version <X.Y>` if the user confirmed
     one at CONFIRM #7 (or one was discovered in `$ODOO_AI_HOME/instances.toml`).
   - If `apply` exits `2` → it is a refuse-to-corrupt signal (invalid JSON
     target). Surface the stderr verbatim and STOP that step; do not retry,
     do not delete anything.
   - If `apply` exits `1` → report the failure, continue to the next step
     only if the steps are independent (browser-deps failing does not block
     instance-profile).
d. A consent line declined: skip that step and note the filter that re-runs it.

**Final summary**, in the operator's words first: what works now (an instance URL, the
browsers ready, auto mode on), what was declined and how to come back to it, what failed
with its one-line cause; then the engine table: each step → `configured` / `skipped (already
done)` / `skipped (declined)` / `failed`. List any served lease older than 7 days that another
session holds (`lease_list` scope `all`, `age_s`) with the `lease_gc` remedy. Then remind the user:
> `/reload-plugins` reloads the plugin's own servers (odoo-local, odoo-media) and their
> options; the browser families step 10 registers in your user configuration and the
> permission rules take effect in a NEW Claude Code / Codex / Gemini session.

## Step notes (what each `apply` does)

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
  `npx -y playwright install chromium`, installs the pinned Playwright library for the narrated-
  video recorder under the state root (`<state root>/recorder`, never global) and runs
  `video_record.py self-test` (Chromium accepts the fake-microphone flags and records video); a
  failed self-test is reported with its lines, never fixed by guessing. For ffmpeg it ONLY prints
  install guidance - it never runs sudo/apt. It never calls `claude mcp add`; registering is
  exclusively step 10/12's job.
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
- **36-claude-tmpdir** - offers to keep Claude Code's own temporary files (session scratchpads,
  background task output, pasted images, edit diffs) under the state root instead of the system
  temporary directory, which on many machines is memory-backed and is never cleaned by Claude
  Code. Run `"$STEPS_DIR/36-claude-tmpdir.sh" propose` and read `ACTION`:
  `set-in-environment` / `set-in-settings` -> the user already chose a directory; report the
  `NOTE` and move on. `settings-invalid` -> report the `NOTE` (the settings file must be fixed
  first). `propose` -> put the `QUESTION` to the user with AskUserQuestion, with
  `CURRENT_TEMP_ROOT`, whether it is memory-backed and the `TARGET`; relay a `NOTE` when one is
  printed. Only on a yes run `"$STEPS_DIR/36-claude-tmpdir.sh" apply --yes`; on a no, run
  nothing. It creates the directory for the user alone and writes one `env` entry in the USER
  settings file, never a project or local one, and never changes a value already set. The
  change applies to Claude Code sessions started afterwards: say so. From then on, each session
  end removes what a session left there once nothing in it changed for `SWEEP_MAX_AGE_DAYS`
  days. Honours `ODOO_AI_NO_CLAUDE_TMP=1`.
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
  rebuild re-applies them (`--no-recorded` / `--no-override` drop them). One venv per profile:
  a venv that another row also uses is never rebuilt under them - this row gets its own
  (`SPLIT_FROM=` names the shared one, which stays for the other rows until each is rebuilt
  too, then it is removed: `REMOVED_SHARED_VENV=`); the plan says so per row. A
  `SUGGESTED_EXTRA=` line names a lint package an addon's tests import; offer it as `--extra`,
  never add it yourself.
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
  (`odoo-bin` with no developer option, or `docker compose up -d`), polls the instance's start page
  until it answers HTTP 200, prints the URL. The series comes from CONFIRM #7 (never silently
  defaulted). The Python interpreter comes from the instance `python` field /
  `$ODOO_PYTHON` / `python3`.
