# Instance cluster (AI-1 to AI-6, CONFIRM #1 to #7), refresh mode, fork resolution

Contents: Instance cluster (AI-1 OSM probe, AI-2 repo set, AI-3 local repos, AI-4 venv scan, AI-5 DB local auth,
AI-6 server-wide modules, CONFIRM #7) - Refresh mode - Fork resolution.

## Instance cluster

**Instance cluster - OSM-grounded propose-then-confirm (AI-1 through AI-5).**
This cluster runs when the filter is `all` or `instance`. It precedes the
numbered step scripts `40`/`45`/`46`/`48`/`50` and drives them with confirmed data.
AI-5 and AI-6 are INSIDE this cluster.

**AI-1 - OSM version + profile probe (CONFIRM #1)**

Call `mcp__plugin_odoo-semantic-mcp_odoo-semantic__list_available_versions` and
`mcp__plugin_odoo-semantic-mcp_odoo-semantic__list_available_profiles` (no arguments). Then DECIDE before asking:
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
mcp__plugin_odoo-semantic-mcp_odoo-semantic__profile_inspect(method='repos', name=<profile>, odoo_version=<version>)
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
  command: git clone with -b BRANCH, --no-single-branch, SSH_URL, into a local directory
  named the way the matched clones on this machine are named (none to follow:
  `<repo>_<series>`) - where BRANCH and SSH_URL come from OSM at runtime
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
- `$ODOO_AI_HOME/venvs/<series>-<profile>` (host-global; the path `45 create-venv` gives a
  new instance).
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
   `mcp__plugin_odoo-semantic-mcp_odoo-semantic__find_examples(query='server_wide_modules', odoo_version=<X.Y>,
   profile_name=<profile>, limit=20)` and take every module whose code tests ITS OWN name
   against `server_wide_modules`. Such checks usually run at import time in a module's
   `__init__.py`: an empty answer is never evidence of "none" - step 1 is the primary source. Then, for every candidate from any
   source, call `mcp__plugin_odoo-semantic-mcp_odoo-semantic__check_module_exists(name=<module>,
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
- AI-3: `fork_facts.py --summary` prints `FORK_KNOWN_OWNERS` (from the given clones and every
  repository the machine's instance catalog holds), one `FORK_ORIGIN_WITHOUT_FORK` per origin
  none of whose given clones has a pushed fork, and `FORK_QUESTION` only when no owner is known.

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
