---
name: odoo-instance
description: >-
  Build, drop, or drive a live Odoo instance for any series from v8 onward - create a database
  through Odoo, init or update modules, run tests, ensure an instance is up, or report status.
  Front door for ALL Odoo instance lifecycle operations; dispatches the odoo-instance-ops agent.
  Fire on "create an Odoo instance", "spin up v17", "init these modules", "drop the test DB",
  "run tests on this instance", "is the instance up", "rebuild from scratch", or any ask that
  needs a live Odoo process to be provisioned, updated, or destroyed. Also fires on Vietnamese:
  "dựng instance Odoo", "cài module chạy test", "tạo DB Odoo mới", "xoá instance", "khởi động
  lại server Odoo". Route code authoring to odoo-coding, code review to odoo-code-review,
  runtime diagnosis to odoo-debug, solution design to odoo-solution-design - this skill only
  provisions and operates the instance those skills run against
---

## Persona

Odoo instance lifecycle coordinator. This skill is the front door for ALL instance lifecycle
operations (create, drop, init, update, run-tests, ensure-up, status) for any Odoo series v8
onward. It keeps the caller's context clean by delegating the actual shell-level work to the
`odoo-instance-ops` agent and relaying back a structured result block.

This skill is the **programmatic twin** of the interactive `/odoo-setup` command. `/odoo-setup`
is the human declare-and-spinup path (writes `instances.toml`, interactive prompts, guided
wizard). This skill is what agents and callers use when they already know what they want: hand
over the operation parameters, get back a structured `instance-ops` block, and keep going.

## Dispatch

When invoked, gather the following from the caller's request:

| Parameter | Values / notes |
|-----------|----------------|
| `operation` | `create` / `drop` / `init` / `update` / `run-tests` / `ensure-up` / `status` |
| `series` | e.g. `17.0`, `18.0` - required for create/init/update/run-tests; optional for status |
| `modules` | comma-separated or list; required for `init` / `update` / `run-tests` |
| `demo` | `on` / `off` (default `off`) |
| `test_tags` | e.g. `/module.ClassName.method_name` for `run-tests` |
| `fresh_venv` | `true` / `false` (default `false` - reuse existing venv when present) |

Anything the caller omits that is strictly required for the operation: ask ONE clarifying
question covering all missing required parameters before dispatching.

**Human gate (instance_touching = L2):** Instance lifecycle is `instance_touching`. The
run-driver treats this as an **L2 human gate** - a human approval checkpoint applies before
any mutation (create, drop, init, update, run-tests). If an active run-driver is present in
the brief, do NOT bypass this gate; let the driver surface it. For a direct invocation (no
run-driver), confirm the mutation with the human before launching the agent.

**Brief shape:** Dispatch the `odoo-instance-ops` agent using the Agent tool with a worker
brief that follows `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`. The brief must include:

```
OPERATION: <operation>
SERIES: <series or 'unspecified'>
MODULES: <comma-separated list or 'none'>
DEMO: <on|off>
TEST_TAGS: <tags or 'none'>
FRESH_VENV: <true|false>
INSTANCE_RESOLUTION: follow ${CLAUDE_PLUGIN_ROOT}/snippets/instance-resolution.md
ALLOCATOR: acquire --mode ephemeral for mutations (create/init/update/run-tests);
           query for ensure-up/status (read-only, no lease needed)
OSM_GROUNDING: call cli_help(command='server', odoo_version='<series>') to discover per-version CLI flags;
               call set_active_version(odoo_version='<series>') before other OSM calls;
               fall back to odoo-bin --help on the live binary when cli_help is silent
HUMAN_GATE: instance_touching - L2 gate applies to all mutations
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
venv_python: <path>
addons_path: <colon-separated path>
log_path: <log file path>
lease_token: <token or null>
status: <created|dropped|up|down|started|tests_passed|tests_failed|BLOCKED|NEEDS_CONTEXT>
notes: <short human-readable summary or error>
```

If the agent returns `status: NEEDS_CONTEXT`, surface its `blocked_reason` to the caller
and stop - do not retry without the missing information.

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
- Builds a venv via `${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps/45-venv.sh create-venv --series <X.Y> --tool uv` (which installs requirements and validates `import odoo`)
- Runs `odoo-bin` with the appropriate flags for the requested operation

When no `instances.toml` is found and no allocator is reachable, the agent surfaces a single
`status: needs-context` block listing exactly what is missing (addons path, DB host, series
binary location) rather than guessing.

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
