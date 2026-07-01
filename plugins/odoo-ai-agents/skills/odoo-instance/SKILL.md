---
name: odoo-instance
argument-hint: "[create|drop|init|update|test|load-language] [version|db]"
description: >-
  Build, drop, or drive a live Odoo instance for any series from v8 onward - create a database
  through Odoo, init or update modules, run tests, ensure an instance is up, or report status.
  Front door for ALL Odoo instance lifecycle operations; dispatches the odoo-instance-ops agent.
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
drop, init, update, run-tests, ensure-up, status, load-language) for any Odoo series v8 onward. Keeps the
caller's context clean by delegating shell-level work to the `odoo-instance-ops` agent and
relaying back a structured result block.

This skill is the **programmatic twin** of the interactive `/odoo-setup` command. `/odoo-setup`
is the human declare-and-spinup path (writes `instances.toml`, interactive prompts, guided
wizard); this skill is for agents/callers who already know what they want: hand over the
operation parameters, get back a structured `instance-ops` block, and keep going.

## Dispatch

When invoked, gather the following from the caller's request:

| Parameter | Values / notes |
|-----------|----------------|
| `operation` | `create` / `drop` / `init` / `update` / `run-tests` / `ensure-up` / `status` / `load-language` |
| `series` | e.g. `17.0`, `18.0` - required for create/init/update/run-tests; optional for status |
| `modules` | comma-separated or list; required for `init` / `update` / `run-tests` |
| `demo` | `on` / `off` (default `off`) |
| `test_tags` | e.g. `/module.ClassName.method_name` for `run-tests` |
| `mode` | `fresh` / `reuse` (default `fresh`; `run-tests` only) - auto `reuse` when reusing an INSTANCE_HANDLE whose DB already has the modules installed, else `fresh`; `fresh` -> `-i` (init+test on a new DB), `reuse` -> `-u` (re-run where `-i` would be a no-op) |
| `log_mode` | `warn` / `info` / `debug` / `sql` (optional; `run-tests` only) - sets the odoo log verbosity; omitted keeps `--log-level=test` |
| `fresh_venv` | `true` / `false` (default `false` - reuse existing venv when present) |
| `languages` | csv locale codes (e.g. `vi_VN,fr_FR`); required for `load-language`; optional for `create` / `init` to activate locales in the same run |
| `skip_auto_install` | `true` / `false` (default `false`; forced `true` when `context=doc`) - adds `--skip-auto-install` so `auto_install` modules do not install alongside the target |
| `context` | `doc` / `default` (default `default`; `doc` auto-sets `demo=on` + `skip_auto_install=true` for a clean documentation instance) |
| `mode_hint` | `path-incremental` / `default` (default `default`; `path-incremental` signals the agent to keep the EXCLUSIVE lease alive across a sequential delta-install loop on ONE DB - do not release between steps; set by `odoo-doc-planner` / `module-packaging` workflow for dependency-cluster doc; do not set manually unless acting as a doc-planner) |

Anything the caller omits that is strictly required for the operation: ask ONE clarifying
question covering all missing required parameters before dispatching.

**Human gate (instance_touching = L2):** Instance lifecycle is `instance_touching`. The
run-harness treats this as an **L2 human gate** - a human approval checkpoint applies before
any mutation (create, drop, init, update, run-tests). If an active run-harness is present in
the brief, do NOT bypass this gate; let the driver surface it. For a direct invocation (no
run-harness), confirm the mutation with the human before launching the agent.

**Brief shape:** Launch the `odoo-instance-ops` agent as a subagent with a worker
brief that follows `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`. The brief must include:

```
OPERATION: <operation>
SERIES: <series or 'unspecified'>
MODULES: <comma-separated list or 'none'>
DEMO: <on|off>
TEST_TAGS: <tags or 'none'>
MODE: <fresh|reuse>           # run-tests only; auto reuse when reusing an INSTANCE_HANDLE whose DB has the modules, else fresh
LOG_MODE: <warn|info|debug|sql or 'default'>   # run-tests only; 'default' keeps --log-level=test
FRESH_VENV: <true|false>
INSTANCE_RESOLUTION: follow ${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md
ALLOCATOR: acquire --mode ephemeral for mutations (create/init/update/run-tests);
           query for ensure-up/status (read-only, no lease needed)
OSM_GROUNDING: call cli_help(command='server', odoo_version='<series>') to discover per-version CLI flags;
               call set_active_version(odoo_version='<series>') before other OSM calls;
               fall back to odoo-bin --help on the live binary when cli_help is silent
HUMAN_GATE: instance_touching - L2 gate applies to all mutations
LANGUAGES: <csv locales or 'none'>
SKIP_AUTO_INSTALL: <true|false>
CONTEXT: <doc|default>
MODE_HINT: <path-incremental|default>
```

**Relay the result:** After the agent finishes, relay its structured output block verbatim
to the caller:

```instance-ops
op: <create-instance|drop-instance|init-modules|update-modules|run-tests|ensure-up|status>
series: <X.Y>
dbname: <db_name>
http_port: <port or null>
gevent_port: <port or null (omit if not bound)>
modules_installed: [<list or null>]
demo: <true|false>
languages_loaded: [<list or null>]      # load-language: locales verified active in res.lang
venv_python: <path>
addons_path: <colon-separated path>
log_path: <log file path>
failed: <n or null>            # run-tests only; from TEST_FAILED=
errors: <n or null>           # run-tests only; from TEST_ERROR=
warnings: <n or null>         # run-tests only; from TEST_WARNING=
findings_path: <path or null> # run-tests only; from FINDINGS_PATH= (failures + warnings file)
lease_token: <token or null>
status: <created|dropped|up|down|started|tests-passed|tests-passed-with-warnings|tests-failed|BLOCKED|NEEDS_CONTEXT>
notes: <short human-readable summary or error>
```

This `instance-ops` block IS the canonical `INSTANCE_HANDLE` for the run: the calling orchestrator
forwards it (`dbname` / `http_port` / `addons_path` / `venv_python` / `lease_token`) as an
`INSTANCE_HANDLE:` field into every downstream code / test brief, and downstream agents consume it
instead of self-provisioning a DB / port / addons_path. Contract:
`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md`.

If the agent returns `status: NEEDS_CONTEXT`, surface its `blocked_reason` to the caller
and stop - do not retry without the missing information.

### Multi-instance parallel provisioning

The allocator issues each concurrent caller an independent ephemeral lease (distinct `dbname`
plus port pool). Safe cap is approximately 3 simultaneous ephemeral instances before RAM and
port-pool pressure increases; the allocator enforces port uniqueness but does not impose a count
ceiling - the orchestrator manages the budget. Use `CONTEXT: doc` to provision clean
documentation instances (demo on + skip-auto-install; target module only, no auto_install
noise). For browser-bound capture workers, cap at W workers equal to the number of distinct
browser server families available (2 headless; optionally +2 headed when DISPLAY is present);
state-mutating scenario drives stay <= 2 simultaneous. Browser-free provisioning phases
(feature-map, icon, copy) can fan out wider. Never create or drop databases with raw
`createdb`/`dropdb` - always through Odoo and the allocator.

## Out of Scope

- **Writing or reviewing application code** - route to `odoo-coding` or `odoo-code-review`
- **Debugging application logic or runtime errors** - route to `odoo-debug`
- **Designing a technical solution** - route to `odoo-solution-design`
- **Translating a module** - route to `odoo-i18n`
- **Interactive declare-and-spinup of `instances.toml`** - that is `/odoo-setup` (human wizard);
  this skill is for programmatic dispatch where the caller already knows the parameters

## Standalone-first fallback

When OSM (the `odoo-semantic-mcp` server) is unreachable, the dispatched `odoo-instance-ops` agent falls
back to reading per-version CLI flags directly from `odoo-bin --help` on the live binary.
The instance provisioning work never degrades - only OSM-grounded CLI discovery degrades to
a local fallback.

When no instance or venv exists on the machine, the agent builds one from scratch:
- Discovers or creates a Python venv for the target series
- Builds a venv via `${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps/45-venv.sh create-venv --series <X.Y> [--profile <name>] --tool uv` (which installs requirements and validates `odoo-bin --version` - not a bare `import odoo`)
- Runs `odoo-bin` with the appropriate flags for the requested operation

When no `instances.toml` is found and no allocator is reachable, the agent surfaces a single
`status: needs-context` block listing exactly what is missing (addons path, DB host, series
binary location) rather than guessing.

For `load-language` specifically: when OSM is unreachable, the agent reads the per-version
language-loading flag directly from `odoo-bin --help` on the live binary and proceeds; the
`res.lang` active verification step (which requires the live Odoo MCP) is skipped and flagged
`grounded: log-signal (not live-verified)` in the output block notes.

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
- `set_active_version(odoo_version='17.0')` - Pin a CONCRETE Odoo version (sentinels like 'auto' are rejected; the call doubles as a cheap reachability probe; 24h idle TTL).

**Primary tools:**
- `cli_help` - Look up odoo-bin subcommand flags, their status, and replacement for deprecated flags.
- `list_available_versions` ☆ - Enumerate which Odoo versions the server has indexed.
<!-- END GENERATED TOOLS -->
