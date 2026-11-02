# odoo-instance - parameters, rules and brief shape

Contents: Parameters | Park vs drop | GATE_ROLE resolution | Log verbosity | Confirmation | Brief shape

Each section is the full wording of the same-named rule that `SKILL.md` summarises. Active-wait, completion, build facts, the agent-side union, inline mode and the relay block: `dispatch-detail.md`. Launch by default and its inline exceptions (a)-(d): `SKILL.md` only.

## Parameters

| Parameter | Values / notes |
|-----------|----------------|
| `operation` | `create` / `drop` / `park` / `resume` / `init` / `update` / `run-tests` / `ensure-up` / `status` / `load-language` |
| `series` | the Odoo series - required for create/init/update/run-tests/resume; optional for status |
| `lease_token` | required for `park` - the `lease_token` field of the `INSTANCE_HANDLE` being finished with. Not used by any other operation. `park` and `drop` of a lease the CALLER holds run inline (exception (d)), never via `odoo-instance-ops` |
| `park_ttl_s` | optional for `park` - how long the suspended database is kept before a gc may reclaim it. Omitted keeps the tool's default; state the default in the relay when the caller named none |
| `persist` | What a CALLER may request: `ephemeral` (default) / `exclusive-running` / `shared-running`. Meanings, and the `exclusive-parked` state a suspended instance sits in: `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` § 5. An `exclusive-running` instance never converges on `8069` (its port comes from the allocator pool); a `shared-running` one is shared by every reader on that series |
| `run_id` | the caller's run id - threaded into every brief and passed to every lease tool as the lease owner. A lease tool called with no `run_id` is refused (`RUN_ID_REQUIRED`). Never invent one: a caller that gave none gets `NEEDS_CONTEXT(RUN_ID)` |
| `PROFILE` | Tenant profile name (the exact name a profile listing returns). Resolve it per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md` (rung 2 returns the exact declared `profile` for the `[[instance]]` covering this repo - use it verbatim) and thread it through, unless the caller passes it (`odoo-doc-site` does: the profile part of the site row's `instance` key). A profile reaches `lease_acquire` as its `profile` ONLY when `catalog_read` (that `series`, that profile) returns a row; the acquire refuses a name no row declares (`NO_INSTANCE`), and an omitted profile takes the series' first row. An EMPTY `INST_PROFILE` from rung 2 means rung 2 did not answer this fact: fall through to the rungs below, and if none names one, OMIT the field rather than send `PROFILE: ''`; an empty `INST_PROFILE` never discards `INST_SERIES`. REQUIRED input for `odoo-instance-ops` § Lint modules - installed ONLY for the designated pre-PR lint gate (HARD RULE) - when omitted, the agent resolves the series' vanilla profile itself or BLOCKs rather than probe unprofiled |
| `modules` | comma-separated or list; required for `init` / `update` / `run-tests`. A caller driving a plan node passes that node's `modules` list here. For the stand-alone proof and for acceptance the install set is the node's modules ONLY; a dependent or a sibling is added only in the second, explicitly requested build (`${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md`) |
| `demo` | `on` / `off` - whether an `init` / `create` build must carry demo data; it reaches `instance_build` as its `demo` argument. Set it from the build's PURPOSE per `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build PURPOSE. **There is no flat default** - omitted, the agent derives the value from the purpose and BLOCKs where the purpose does not resolve and the output depends on demo. `run-tests` takes NO `demo`: a test build runs the series default - never set it for a test dispatch |
| `test_tags` | `run-tests` scope selector (`modules` builds the registry, `test_tags` decides whose tests run). Pass the caller's resolved blast radius, normally `/<m>` per module in `modules` (e.g. `/sale,/account`), narrowable to a class or method (`/module:ClassName.method_name` - the CLASS separator is a COLON) for a focused re-run. `full` = run untagged ON PURPOSE (release sweep, CI/Runbot parity, no-code-change smoke). OMITTED / `none` = not supplied: the agent DERIVES `/<m>` per module and never runs untagged. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md`; which modules belong in the set: `${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md` |
| `GATE_ROLE` | `pre-pr-lint-gate` / `node-verify` - REQUIRED for `run-tests`, and any `init`/`update` dispatch whose purpose is running automated tests via `--test-enable`; decides whether the agent unions the lint-class modules into the install list + `--test-tags` (`references/dispatch-detail.md` § Build facts the tools apply and the agent-side union). `pre-pr-lint-gate` is reserved for the ONE run-level pre-PR lint-class gate (the plan's `integrate` node states it explicitly); every OTHER test-run caller (a node verification run, a leaf's own break-check run, an ad-hoc human "run the tests" request) is `node-verify`. This skill resolves it before dispatch (rule below) |
| `mode` | `fresh` / `reuse` (`run-tests` only) - decided on the DATABASE: `reuse` whenever the target database already has the modules installed, `fresh` only for the FIRST install onto a brand-new database; `fresh` -> `-i` (init+test), `reuse` -> `-u` (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Test run on an existing database) |
| `hand_on` | `yes` / `no` (default `no`; `run-tests` with `mode=fresh` only) - `yes` keeps the lease and forwards its `INSTANCE_HANDLE` to the caller, who owns it from then on; `no` releases it when the run ends |
| `log_mode` | `info` / `debug` / `sql` (optional; `run-tests` only) - overrides the odoo log verbosity for this run; omitted keeps the default (§ Log verbosity). `warn` is REFUSED - it hides the pass summary |
| `fresh_venv` | `true` / `false` (default `false` - build on the venv the catalog declares for the series). `true` makes the executor rebuild the series' venv before it acquires a lease; a catalog row with no venv at all gets one built the same way without asking. Never combine `true` with a forwarded `INSTANCE_HANDLE`: that lease fixes the interpreter |
| `languages` | csv locale codes (e.g. `vi_VN,fr_FR`); required for `load-language`; optional for `create` / `init` / `run-tests`. It reaches `instance_build` as its `languages` argument; the tool adds `en_US` to every build, so neither the caller nor this skill adds it; omit / pass `none` for `en_US` alone |
| `skip_auto_install` | `true` / `false` (default `false`; forced `true` when `context=doc`) - the executor adds the skip-auto-install flag to every build of the dispatch, where the series' `cli_help` lists it |
| `context` | `doc` / `default` (default `default`; `doc` auto-sets `demo=on` + `skip_auto_install=true` for a clean documentation instance) |
| `mode_hint` | `path-incremental` / `default` (default `default`). `path-incremental` = ONE lease held across a sequential delta-install loop on ONE DB (dependency-cluster documentation). It ALWAYS runs INLINE in the driving skill's context per `references/dispatch-detail.md` § Inline mode (`MODE_HINT: path-incremental`) and is NEVER dispatched to `odoo-instance-ops` |
| `WORKTREE_PATH` | (optional) absolute path to the worktree whose code this instance must load. When set, the executor re-roots the addons list passed to `lease_acquire` onto it per `references/worktree-addons-path.md`. Omit for a catalog-tree instance |

Anything the caller omits that is strictly required for the operation: ask ONE clarifying
question covering all missing required parameters before dispatching.

## Park vs drop

**`park` vs `drop` - decide on a fact about the DATABASE.** `park` KEEPS the database, filestore and
ports so a later `resume` picks the instance up where it was; `drop` destroys the database. A caller
finished with the instance FOR NOW but still wanting its data gets `park` - never a `drop` dispatch
in the hope it will be declined. `resume` brings a parked instance back on its own coordinates and
never rebuilds or installs modules.

## GATE_ROLE resolution

**`GATE_ROLE` resolution (mandatory, resolved by THIS skill before dispatch).** For any `run-tests`
(or test-enable `init`/`update`) request: an explicit value already present in the caller's context
(the plan's pre-PR lint gate, or `odoo-coder`'s own node test) wins - forward it verbatim. For a
direct/human-initiated invocation with no stated role, use `GATE_ROLE: node-verify` and state the
assumption. Forward `GATE_ROLE: pre-pr-lint-gate` only when the caller explicitly identifies itself
as that ONE gate - never inferred from module count, phrasing, or any other proxy. The dispatched
`odoo-instance-ops` agent always receives a resolved `GATE_ROLE`.

## Log verbosity

**Log verbosity default.** Every build (`create` / `init` / `update` / `run-tests`) runs at
`--log-level=info`. Override per dispatch: `run-tests` via `log_mode`; the rest via a `--log-level`
in the brief's extra flags, which is placed after the default and wins. Ground `--log-level` via
`cli_help` like any other flag.

## Confirmation

**Confirmation.** `create`, `init`, `update` and `run-tests` run without asking. Ask the human in
text (`approve / skip / cancel`) only before a `drop` of a database this run did not create; a
`drop` of a database created in this run proceeds. `park` and `resume` never ask.

## Brief shape

**Brief shape:** Launch the `odoo-instance-ops` agent with a worker brief per
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`. When composing the dispatch prompt for any
specialist agent you dispatch, fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` § Universal skeleton (read it by path) plus the target agent's
family delta; never inline that file verbatim into a hard-leaf brief. The brief must include:

```
OPERATION: <operation>
SERIES: <series or 'unspecified'>
PROFILE: <the NON-EMPTY profile name this skill already resolved before composing this brief;
  omit the field entirely when the resolved value is empty or no rung named one -
  never emit PROFILE: '' and never forward a pointer for the agent to go re-resolve>
MODULES: <comma-separated list or 'none'>
DEMO: <on|off>                # init/create only; omitted on run-tests - the series default applies
TEST_TAGS: <the resolved scope tags (normally `/<m>` per module in MODULES), or 'full' to run
  untagged on purpose; 'none'/omitted means NOT SUPPLIED and the agent derives `/<m>` per module -
  it never means "run every installed module's suite">
GATE_ROLE: <pre-pr-lint-gate|node-verify>   # REQUIRED for run-tests / test-enable init/update; resolved per § GATE_ROLE resolution - never omitted, never left for the agent to guess
MODE: <fresh|reuse>           # run-tests only; reuse whenever the target DB already has the modules, fresh only for a first install on a new DB
LOG_MODE: <info|debug|sql or 'default'>   # run-tests only; 'default' keeps the build default
FRESH_VENV: <true|false>
PERSIST: <ephemeral|exclusive-running|shared-running>   # create only; default ephemeral - `${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-MODES.md` § 5
HAND_ON: <yes|no>             # run-tests fresh only; yes = keep the lease and forward its INSTANCE_HANDLE; default no = release it
LEASE_TOKEN: <token of the lease to suspend>            # park only - REQUIRED there, omitted everywhere else
PARK_TTL_S: <seconds or 'default'>                      # park only; 'default' keeps the tool's own budget
INSTANCE_HANDLE: <the caller's forwarded handle, verbatim>    # omit when none; every operation then runs on that lease/database (ensure-up serves it)
RUN_ID: <the caller's run id>                           # ALWAYS set - the lease-ownership identity; never invent one
LANGUAGES: <csv target locales, or 'none'; the tool adds en_US to every build>
SERVER_WIDE: <{exclude: [...], include: [...]} from the caller's brief, verbatim>   # omit unless the caller names one; the catalog row's set applies
SKIP_AUTO_INSTALL: <true|false>
CONTEXT: <doc|default>
WORKTREE_PATH: <absolute worktree path, or 'none'>   # when set, the agent re-roots its lease's addons list onto it
SHARE_DIR: <the run's captured absolute SHARE path - substitute it, never re-resolve>
ISOLATE_DIR: <the run's captured absolute ISOLATE path - substitute it, never re-resolve; the agent appends the run worklog and must not key it on WORKTREE_PATH's own toplevel>
```

`INSTANCE_RESOLUTION`, `ALLOCATOR`, and `OSM_GROUNDING` are NOT brief fields: the dispatched agent's
own "Common preamble" (Steps A-D) and port-flag tie-break own that procedure. Never add a field whose
value is a procedure to follow rather than a value this skill already resolved.
