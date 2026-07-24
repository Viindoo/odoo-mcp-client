---
name: odoo-instance
argument-hint: "[create|drop|init|update|test|load-language] [version|db]"
description: >-
  Build, drop, or drive a live Odoo instance for any series from v8 onward - create a database
  through Odoo, init or update modules, run tests, ensure an instance is up, or report status.
  Front door for ALL Odoo instance lifecycle operations and the ONLY dispatcher of the odoo-instance-ops agent.
  Fire on "create an Odoo instance", "spin up v17", "init these modules", "drop the test DB",
  "run tests on this instance", "is the instance up", "rebuild from scratch",
  "activate a language", or any ask that needs a live Odoo process to be provisioned, updated,
  or destroyed. Also fires on Vietnamese: "dựng instance Odoo", "cài module chạy test",
  "tạo DB Odoo mới", "xoá instance", "khởi động lại server Odoo", "nạp ngôn ngữ". Route code authoring to odoo-coding, code review to odoo-code-review,
  runtime diagnosis to odoo-debug, solution design to odoo-solution-design - this skill only
  provisions and operates the instance those skills run against
---

## Role

Odoo instance lifecycle coordinator. Front door for ALL instance lifecycle operations (create,
drop, init, update, run-tests, ensure-up, status, load-language) for any Odoo series v8 onward.
Keeps the caller's context clean by delegating shell-level work and relaying a structured result
block. Programmatic twin of the interactive `/odoo-setup` command (the human declare-and-spinup
wizard that writes `instances.toml`): use this skill when the caller already knows the operation
parameters - hand them over, get back a structured `instance-ops` block.

**Single owner of instance provisioning.** This skill is the SINGLE PLACE that OWNS Odoo instance
fan-out: any component needing a live instance routes here via the Skill tool instead of driving
the lifecycle itself, so the L2 human gate, instance-allocation rules, and HARD RULES (`en_US`
union, Viindoo `to_base`, lint-module install, per-version `cli_help` grounding) are enforced in
one place. **When the caller is a declared HARD LEAF (`agents.<name>.role == leaf` in the
agent-role SSOT, `generator/skill_tool_deps.json`), this skill MUST provision INLINE (see "Inline
leaf-mode" below) and MUST NOT launch the `odoo-instance-ops` agent** - inline leaf-mode is
mandatory for a leaf caller, not a judgment call. For a spawner/coordinator/skill caller, provision
the way that fits the caller's context - run the ops steps INLINE in the caller's own context (see
"Inline leaf-mode" below), or launch the `odoo-instance-ops` agent per "Brief shape" below; this
skill is the component that owns launching that agent - the agent-launch path is available only to
spawner/coordinator/skill callers, never to a hard-leaf caller. However the
operation is carried out, the SAME HARD RULES apply - the inline path is not a bypass. A provided
`INSTANCE_HANDLE` ALWAYS wins over self-provisioning either way (contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`), and neither path ever calls
`scripts/lib/allocator.py` directly - that would skip the HARD RULES this skill enforces.

Instance-ops work does not vary by domain complexity: the `odoo-instance-ops` agent runs at a flat
`sonnet` tier when launched - there is deliberately NO per-operation model-tier table to drift.

## Dispatch

When invoked, gather the following from the caller's request:

| Parameter | Values / notes |
|-----------|----------------|
| `operation` | `create` / `drop` / `init` / `update` / `run-tests` / `ensure-up` / `status` / `load-language` |
| `series` | e.g. `17.0`, `18.0` - required for create/init/update/run-tests; optional for status |
| `persist` | `ephemeral` / `exclusive-running` / `shared-running` (default `ephemeral`) - the instance lifetime + isolation `create` needs: `ephemeral` = throwaway mutation build (`--stop-after-init`, unique db, no listening port); `exclusive-running` = a live, listening instance that is MINE (unique db + an allocator-issued pooled port + my `run_id` recorded as lease owner - use for mutating work that must stay up; never converges on `8069`); `shared-running` = attach to / register the SHARED read-only render target for this series (still owner-stamped with `run_id` so it cannot be foreign-bare-dropped). The judgment call: will the caller MUTATE and need the process to stay listening (`exclusive-running`) vs a read-only view of the shared target (`shared-running`) vs a throwaway build with no listener (`ephemeral`) |
| `run_id` | the caller's session/run id - threaded into every brief and forwarded to the allocator as the lease owner. NEVER omit it: an unowned live lease is what lets another session drop yours |
| `PROFILE` | Viindoo tenant profile name, e.g. `viindoo_17`; this skill reads `viindoo_profile` from `context.md` (Tier-2 SHARE - resolve via the resolve-capture-substitute protocol in `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`, captured path shown as `<SHARE_DIR>` below - `<SHARE_DIR>/context.md`) and threads it through - the caller never sets this manually; omit from the brief when `<SHARE_DIR>/context.md` has no `viindoo_profile` field. REQUIRED input for the agent's `to_base`/lint-module HARD RULEs below - when omitted, the agent resolves the series' vanilla profile itself or BLOCKs rather than probe unprofiled |
| `modules` | comma-separated or list; required for `init` / `update` / `run-tests` |
| `demo` | `on` / `off` (default `off`) |
| `test_tags` | e.g. `/module.ClassName.method_name` for `run-tests` |
| `mode` | `fresh` / `reuse` (default `fresh`; `run-tests` only) - auto `reuse` when reusing an INSTANCE_HANDLE whose DB already has the modules installed, else `fresh`; `fresh` -> `-i` (init+test on a new DB), `reuse` -> `-u` (re-run where `-i` would be a no-op) |
| `log_mode` | `warn` / `info` / `debug` / `sql` (optional; `run-tests` only) - sets the odoo log verbosity; omitted keeps `--log-level=test` |
| `fresh_venv` | `true` / `false` (default `false` - reuse existing venv when present) |
| `languages` | csv locale codes (e.g. `vi_VN,fr_FR`); required for `load-language`; optional for `create` / `init` - this skill ALWAYS unions `en_US` into the activation set before dispatch (see "en_US is mandatory on every build" below), so the caller never needs to add it; omit / pass `none` to activate `en_US` alone |
| `skip_auto_install` | `true` / `false` (default `false`; forced `true` when `context=doc`) - adds `--skip-auto-install` so `auto_install` modules do not install alongside the target |
| `context` | `doc` / `default` (default `default`; `doc` auto-sets `demo=on` + `skip_auto_install=true` for a clean documentation instance) |
| `mode_hint` | `path-incremental` / `default` (default `default`; `path-incremental` signals the agent to keep the EXCLUSIVE lease alive across a sequential delta-install loop on ONE DB - do not release between steps; set by `odoo-doc-planner` / `module-packaging` workflow for dependency-cluster doc; do not set manually unless acting as a doc-planner) |

Anything the caller omits that is strictly required for the operation: ask ONE clarifying
question covering all missing required parameters before dispatching.

**Log verbosity default.** `create` / `init` / `update` builds run at `--log-level=warn` by DEFAULT
(quieter than Odoo's stock `info`); `run-tests` keeps `--log-level=test`. A caller may ESCALATE to
`info` / `debug` - for `run-tests` via the `log_mode` field, for `create` / `init` / `update` via an
extra flag threaded into the brief (overrides the `warn` default). The agent grounds `--log-level`
via `cli_help` like any other flag.

**Active-wait on long builds (relay).** A `create` / `init` / `update` / `run-tests` build can run
longer than the foreground tool timeout. The dispatched `odoo-instance-ops` agent MUST launch the
build in the background and poll `LOG_PATH` to a TERMINAL marker - for init/update, the ONLY success
marker is `Modules loaded.` present AND no failure marker (matching the script's own
`_install_confirmed` verdict, SSOT-shared with the `wait-log` helper's `_scan_build_markers`;
`Registry loaded` / exit 0 / `Initiating shutdown` are progress signals only, never independently
sufficient for success); failure: `Traceback` / ` CRITICAL ` / ` ERROR ` / `Failed to load registry` /
the silent-skip markers (`invalid module names, ignored`, `Some modules are not loaded`, `Unmet
dependenc(y|ies)`, `cannot be installed`); run-tests reuses `TEST_RESULT=` (a skip-only run - `TEST_SKIPPED>0` with no failure - is `TEST_RESULT=inconclusive`, a terminal marker like any other, never a stall). Emit a heartbeat between
polls; the exit code stays authoritative for FAILURE (never let a marker override a non-zero exit)
while the completion marker is still required for SUCCESS - never idle-stalling or returning before a
terminal marker; on timeout it reports `BLOCKED` with `LOG_PATH` preserved. Full contract:
`${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` "Active-wait on long builds".

**Readiness/completion signal is DETERMINISTIC, never a log tail.** Under the `--log-level=warn`
baseline every completion line above is INFO-level and gets suppressed - a clean, successful run
produces an EMPTY log, so waiting to SEE a line in it can stall to the timeout even on success. Two
different, deterministic signals apply instead, one per job shape: an install/update job's DONE
signal is the launched process EXITING (`--stop-after-init` guarantees this), confirmed by exit 0
AND a forced completion marker (`Modules loaded.`, guaranteed present via
`--log-handler=<ns>.modules.loading:INFO`, `<ns>` = `openerp` v8-v9 / `odoo` v10+) AND the absence
of any failure marker - exit 0 ALONE is NOT proof of install (a bad module name, an unresolved
dependency, or a failed demo load can all exit 0 while silently skipping the install). A LISTENING
instance's READY signal is a BOUNDED-timeout HTTP port poll - primary `/web/database/selector`,
fallback `/web/login` - never a log line. Full contract:
`${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` "Deterministic completion contract" and
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-LIFECYCLE.md` item 14.

**`en_US` is mandatory on every build - independent of caller input.** `en_US` is Odoo's
base/source language. Every `create`, `init`, and `run-tests` (`mode: fresh`) dispatch MUST activate
it in the target DB. Before building the brief, compute
`activation_languages = {"en_US"} union languages` (omitted / `none` = empty set) and pass that
UNIONED csv as the brief's `LANGUAGES:` field. This BUILD-TIME guarantee is owned entirely by this skill - no downstream consumer
(translation, doc capture, QA, module reload) may find `en_US` missing. `odoo-i18n` unions `en_US`
into its own activation set too (recipe KT3) because it issues `--load-language` / `i18n loadlang`
directly against `odoo-bin` OUTSIDE this skill's dispatch - a second, independent enforcement point,
not a duplicate.

**Agent-side unions this skill does not compute itself.** This skill resolves `PROFILE` (from
`viindoo_profile` in `<SHARE_DIR>/context.md`, omitted when absent) and threads it into the brief. The
dispatched `odoo-instance-ops` agent then PINS that profile (`set_active_profile` + explicit
`profile_name=` on every probe - never profile-less) and performs two further DATA-DRIVEN unions
before building the `odoo-bin` command, on top of the `en_US` union above - callers pass nothing
extra for either:
- **Viindoo `to_base` on `--load`.** The agent pins the resolved profile (brief `PROFILE`, or the
  series' vanilla profile when absent, or `NEEDS_CONTEXT`) then checks it for `to_base`; when
  present, it unions `to_base` into the server-wide `--load` list (never as an ordinary `-i`) - see
  `${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` "Server-wide modules (`--load`) - Viindoo
  `to_base` (HARD RULE)".
- **Lint modules for `run-tests`.** For a test-run build, the agent reuses that pinned profile to
  probe for `test_lint`/`test_pylint` and unions every present one into BOTH the `-i`/`-u` install
  list and `--test-tags` - see `${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` "Lint modules -
  installed for test-run builds (HARD RULE)" and
  `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md` "Install the lint modules (not just tag them)".

**Config isolation.** No operation writes to a shared or default config path - the CLI-flag path
reads no config file, the generated-conf path is a unique temp file per run; see
`${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION.md §Config-file isolation` for the full
two-path contract.

**Human gate (instance_touching = L2):** Instance lifecycle is `instance_touching` - an L2 human
gate applies before any mutation (create, drop, init, update, run-tests). If a run-harness is in the
brief, do NOT bypass it; let the driver surface it. For a direct invocation, confirm the mutation
with the human before launching the agent.

**Brief shape:** Launch the `odoo-instance-ops` agent with a worker brief per
`${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`. When composing the dispatch prompt for any
specialist agent you dispatch, fill the caller-side skeleton in
`${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md` (read it by path) plus the target agent's
family delta; never inline that file verbatim into a hard-leaf brief. The brief must include:

```
OPERATION: <operation>
SERIES: <series or 'unspecified'>
PROFILE: <viindoo_profile from SHARE_DIR/context.md, or omit if absent>
MODULES: <comma-separated list or 'none'>
DEMO: <on|off>
TEST_TAGS: <tags or 'none'>
MODE: <fresh|reuse>           # run-tests only; auto reuse when reusing an INSTANCE_HANDLE whose DB has the modules, else fresh
LOG_MODE: <warn|info|debug|sql or 'default'>   # run-tests only; 'default' keeps --log-level=test
FRESH_VENV: <true|false>
INSTANCE_RESOLUTION: follow ${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md
PERSIST: <ephemeral|exclusive-running|shared-running>   # create only; default ephemeral - see the dispatch table above
RUN_ID: <the caller's session/run id>                   # ALWAYS set - the lease-ownership identity; never omit
ALLOCATOR: PERSIST=ephemeral -> acquire --mode ephemeral --ports 0 (mutations that need no listener: init/update/run-tests, or a throwaway create);
           PERSIST=exclusive-running -> acquire --mode ephemeral --ports 1 (or 2 when a gevent/longpolling port is needed too) --run-id <RUN_ID> - a LIVE, listening instance that is MINE, never converging on 8069;
           PERSIST=shared-running -> the SHARED render target, owner-stamped via --run-id (never a bare acquire alongside it - the spinup mechanism registers this lease internally);
           query for ensure-up/status (read-only, no lease needed)
OSM_GROUNDING: call cli_help(command='server', odoo_version='<series>') to discover per-version CLI flags;
               call set_active_version(odoo_version='<series>') before other OSM calls;
               fall back to odoo-bin --help on the live binary when cli_help is silent;
               when cli_help lists MORE THAN ONE port-flag candidate for the series, PREFER
               --http-port/--gevent-port whenever present (use --xmlrpc-port only for v8-v10,
               --longpolling-port only where --gevent-port is absent) - never a coin-flip between two listed flags
HUMAN_GATE: instance_touching - L2 gate applies to all mutations
LANGUAGES: <csv locales - ALWAYS unioned with en_US per the build rule above; 'none' -> en_US alone>
SKIP_AUTO_INSTALL: <true|false>
CONTEXT: <doc|default>
MODE_HINT: <path-incremental|default>
```

**Memory cap inheritance.** No separate brief field is needed: the dispatched `odoo-instance-ops`
agent's scripted odoo-bin launches (create/init/update/run-tests) carry the `ulimit -Sv` +
`--limit-memory-hard` guard automatically (sourced from `scripts/lib/resource_limits.sh`),
overridable via `ODOO_AI_LIMIT_MEMORY_HARD`. Policy SSOT (do not restate it here):
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

**Relay the result:** Relay the agent's structured output block verbatim to the caller:

```instance-ops
op: <create-instance|drop-instance|init-modules|update-modules|run-tests|ensure-up|status>
series: <X.Y>
dbname: <db_name>
http_port: <port or null>
gevent_port: <port or null (omit if not bound)>
db_port: <resolved port or empty>
run_id: <owning run id or empty>
modules_installed: [<list or null>]
demo: <true|false>
languages_loaded: [<list or null>]      # load-language: locales verified active in res.lang
venv_python: <path>
addons_path: <colon-separated path>
log_path: <log file path>
failed: <n or null>            # run-tests only; from TEST_FAILED=
errors: <n or null>           # run-tests only; from TEST_ERROR=
warnings: <n or null>         # run-tests only; from TEST_WARNING=
skipped: <n or null>          # run-tests only; from TEST_SKIPPED=
findings_path: <path or null> # run-tests only; from FINDINGS_PATH= (failures + warnings + skips file)
lease_token: <token or null>
status: <created|dropped|up|down|started|tests-passed|tests-passed-with-warnings|tests-inconclusive|tests-failed|BLOCKED|NEEDS_CONTEXT>
notes: <short human-readable summary or error>
```

This `instance-ops` block IS the canonical `INSTANCE_HANDLE` for the run: the orchestrator forwards
it (`dbname` / `http_port` / `db_port` / `addons_path` / `venv_python` / `lease_token` / `run_id`) as
an `INSTANCE_HANDLE:` field into every downstream code / test brief, and downstream agents consume
it instead of self-provisioning. Forwarding `db_port` and `run_id` (not just `http_port` and
`lease_token`) is what lets a later turn drop or release the right instance on the right Postgres
port under the right owner. Contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.

On `status: NEEDS_CONTEXT`, surface its `blocked_reason` and stop - do not retry without the missing
information.

### Inline leaf-mode (dispatched leaf / subagent self-provision)

Run the ops steps INLINE in the caller's own context - without launching the `odoo-instance-ops`
agent. **MANDATORY, not a judgment call, when the caller is a declared HARD LEAF** (`agents.<name>.role
== leaf`) - a hard-leaf caller MUST get inline leaf-mode and this skill MUST NOT launch
`odoo-instance-ops` for it. For a spawner/coordinator/skill caller, use inline leaf-mode whenever
that fits the caller's situation better than launching the agent (see "Single owner of instance
provisioning" above and `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`). This
lets a caller lacking an `INSTANCE_HANDLE` self-provision an isolated ephemeral DB directly, and -
unlike a raw `allocator.py` call - still under the HARD RULES.

A provided `INSTANCE_HANDLE` ALWAYS wins: if one is in the brief, consume it and do NOT provision
(contract: `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`). Only with NO handle does
the caller self-provision via this inline path.

Run these steps in order, honoring the SAME HARD RULES as the agent (single source: the
cross-referenced sections in `${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` - do NOT restate
them here):

1. **Acquire an isolated ephemeral lease** per `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
   § "Odoo instance allocation" (`scripts/lib/allocator.py acquire --mode ephemeral` -> a unique
   `ALLOC_DB_NAME` + ports; never reuse the single declared db/port for a mutation).
2. **Pin series + ground CLI flags** - `set_active_version` then `cli_help` per the agent's "Common
   preamble" Steps A-B (every flag from this series' `cli_help`, never from memory).
3. **Apply the HARD RULES** as the agent does - `en_US` union
   (`${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` "en_US - always loaded on every build"),
   Viindoo `to_base` union into `--load` (same file, "Server-wide modules (`--load`) - Viindoo
   `to_base` (HARD RULE)"), and lint-module install for test-run builds (same file, "Lint modules -
   installed for test-run builds (HARD RULE)"). Resolve + PIN the profile before any probe; never
   probe profile-less.
4. **Run the operation** via `${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps/55-instance-ops.sh`
   (`init` / `update` / `test` / `drop`) with resolved flags in `--extra`, applying the active-wait
   contract above (background launch + poll `LOG_PATH` to a terminal marker; never idle-stall).
5. **Release** the lease when done - you release it UNLESS you forward the handle to a NAMED
   catcher in `next.inputs` (`INSTANCE_HANDLE`, naming the skill that needs the live state); an
   unforwarded live lease at your terminal status is a leak, not a valid handoff. Full rule:
   `${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T0/T1/T4. Either way, emit the
   same `instance-ops` block used when the agent is launched instead, so the caller consumes an
   identical handle either way.

The L2 human gate still applies to any mutation via this path (see "Human gate"): if a run-harness
is present let the driver surface it, else confirm the mutation with the human first.

### Multi-instance parallel provisioning

The allocator issues each concurrent caller an independent ephemeral lease (distinct `dbname` +
port pool). Safe cap is ~3 simultaneous ephemeral instances before RAM / port-pool pressure; the
allocator enforces port uniqueness but imposes no count ceiling - the orchestrator manages the
budget. Use `CONTEXT: doc` for clean documentation instances (demo on + skip-auto-install; target
module only). For browser-bound capture workers, cap W at the number of distinct browser server
families available; state-mutating scenario drives stay <= 2 simultaneous. Browser-free phases (feature-map, icon, copy) fan out wider. Never
`createdb`/`dropdb` raw - always through Odoo and the allocator. `W` is per-family, RAM-permitting
(never a global single-flight across families): `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md`
§ Browser exclusivity is the SSOT for the `W` number; full exclusivity rule + rationale:
`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T2.

## Out of Scope

- **Writing or reviewing application code** - route to `odoo-coding` or `odoo-code-review`
- **Debugging application logic or runtime errors** - route to `odoo-debug`
- **Designing a technical solution** - route to `odoo-solution-design`
- **Translating a module** - route to `odoo-i18n`
- **Interactive declare-and-spinup of `instances.toml`** - that is `/odoo-setup` (human wizard);
  this skill is for programmatic dispatch where the caller already knows the parameters

## Standalone-first fallback

When OSM (the `odoo-semantic-mcp` server) is unreachable, the dispatched `odoo-instance-ops` agent
reads per-version CLI flags directly from `odoo-bin --help` on the live binary. Provisioning never
degrades - only OSM-grounded CLI discovery falls back locally.

When no instance or venv exists, the agent builds one from scratch: discover/create a Python venv
for the target series via `${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps/45-venv.sh create-venv --series
<X.Y> [--profile <name>] --tool uv` (installs requirements and validates `odoo-bin --version` - not
a bare `import odoo`), then run `odoo-bin` with the operation's flags.

When no `instances.toml` and no allocator are reachable, the agent surfaces one
`status: needs-context` block listing exactly what is missing (addons path, DB host, series binary
location) rather than guessing.

For `load-language`: when OSM is unreachable the agent reads the per-version language-loading flag
from `odoo-bin --help` and proceeds; the `res.lang` active-verification step (needs the live Odoo
MCP) is skipped and flagged `grounded: log-signal (not live-verified)` in the output notes.

## MCP tools

<!-- BEGIN GENERATED TOOLS -->
> **Pick the right tool first.** Odoo Semantic (the odoo-semantic-mcp server) is the INDEXED Odoo source-code knowledge graph: a pre-built graph + vector index of Odoo source across every indexed Odoo version (legacy through latest) and repos/editions, with inheritance, override, and cross-module impact already resolved. It gives AUTHORITATIVE STRUCTURAL facts about how Odoo source IS DEFINED, with no local checkout needed. Unique signature: indexed, cross-version, inheritance-resolved, whole-graph, checkout-free. It is a STATIC index with NO runtime/live data.
>
> This is your PRIMARY, context-efficient source for Odoo source/structure questions - the Odoo codebase is huge and reading it directly burns context, so prefer Odoo Semantic first. Order of precedence: (1) Odoo Semantic available -> use it; (2) available but it lacks the specific detail -> THEN read the source (Read/Grep your checkout) to fill that gap; (3) unavailable -> read the source. Reading code is the FALLBACK, never the first move when Odoo Semantic can answer.
>
> Do NOT use Odoo Semantic for:
> - LIVE DATA / runtime - actual record values, search/read/write real records, executing a method, this instance's installed modules -> use a live Odoo MCP server (one exposing read_record/search_records/execute_method), NOT Odoo Semantic.
>
> Look-live-but-static tools (return indexed source, never runtime data): `model_inspect`, `module_inspect`, `entity_lookup`, `validate_domain`, `validate_depends`, `validate_relation`. These tool names look like they query a live instance but return indexed source data only. If you need live records, Odoo Semantic is the wrong server.

**Session bootstrap** (call once at session start):
- `set_active_profile(profile_name='<viindoo_profile from <SHARE_DIR>/context.md>')` - Pin tenant profile for the session so subsequent calls scope to one customer profile.
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `check_module_exists` - Verify module availability, edition (CE/EE/Viindoo), and cross-version presence.
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `list_available_versions` ☆ - Enumerate which Odoo versions the server has indexed.
- `profile_inspect` - Profile-level introspection discriminator (ADR-0028): inspect a tenant profile's composition in one call.
<!-- END GENERATED TOOLS -->
