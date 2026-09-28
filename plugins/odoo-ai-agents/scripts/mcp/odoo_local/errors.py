"""errors.py - the ONE error-code table of the odoo-local MCP server (code -> agent-facing remedy).

Every tool error the server returns carries {code, message, remedy, diagnostics}. `remedy` is looked
up HERE and nowhere else: a handler raises ToolError(code, message) and never writes its own remedy
text, so one code always tells the agent the same thing.

Three sources merge into the table (later wins):
  - the allocator's named-code table, imported lazily by `allocator_codes()` from
    scripts/lib/allocator.py when that module exposes one. It is looked up at first use, not at
    import time, so a missing or mid-edit allocator never stops the server from starting.
  - TOOL_REMEDIES below: the SAME allocator codes re-worded in TOOL vocabulary. The allocator's
    own remedies name its CLI flags (--addons-path-override, --force-forget, `list --tokens`),
    which an agent calling these tools cannot pass; the code and its meaning stay the
    allocator's, only the instruction is translated. A test keeps every key here a live
    allocator code, so a renamed code cannot leave a dead translation behind.
  - SERVER_CODES below: codes the server itself raises (argument validation, helper failures).

A TOOL_REMEDIES value is normally a plain string. A code whose allocator-side refusal SPLITS by
`fields.reason` (today, only PORT_POOL_EXHAUSTED: holders present vs. the pool busy with no lease
holding it - see allocator.py PORTS_BUSY_OUTSIDE_REGISTRY) instead carries
`{"default": <str>, "reasons": {<reason>: <str>}}`; `remedy_for(code, diagnostics)` picks the
`reasons` entry when `diagnostics["fields"]["reason"]` names one, else `default`. This is still
ONE table per code - never a second reason-keyed table alongside it.

Syntax is deliberately kept to what very old Python 3 parses (no f-strings, no annotations): the
entry point imports this module in PYTHON_TOO_OLD degraded mode to report that code with its remedy.
"""

import os
import sys
import threading


def _plugin_root():
    """The plugin's install root (parent of `scripts`), computed from THIS file's location - never
    hardcoded - so a remedy that names a doc under it resolves from ANY install path (marketplace
    cache, --plugin-dir checkout, worktree): odoo_local/errors.py -> odoo_local -> mcp -> scripts ->
    plugin root. A relative doc path in a remedy string is meaningless to an agent whose cwd is a
    user project, not this plugin - every doc reference here MUST be this absolute path."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


# Codes the server raises itself. One imperative line each, written for the executing agent.
SERVER_CODES = {
    "INVALID_ARGUMENTS": "Correct the argument named in the message so it satisfies the tool's inputSchema, then call again.",
    "PYTHON_TOO_OLD": "Make the python3 that Claude Code launches resolve to Python 3.8 or newer and restart the session; until then use the Bash CLI fallback.",
    "INTERNAL": "Do not retry the same call; report the tool name, message and diagnostics to the user.",
    "TOOL_UNAVAILABLE": "Use the Bash CLI fallback in %s for this operation." % os.path.join(
        _plugin_root(), "docs", "reference", "INSTANCE-ALLOCATION-API.md"),
    "CATALOG_UNREADABLE": "Fix the TOML syntax or file permissions of the catalog named in the message, then call again.",
    "PATH_NOT_DIRECTORY": "Pass an absolute path to an existing directory.",
    "PROJECT_DIR_UNRESOLVED": "Pass a cwd inside a git repo or below an Odoo module or .odoo-ai-root marker, or set ODOO_AI_PROJECT_DIR / ODOO_AI_WORKTREE_DIR.",
    "SUBPROCESS_TIMEOUT": "The helper exceeded its time bound and was killed. A killed lease_release, lease_park or lease_gc is taken over by the next call on the same lease (its reclaiming marker names a dead pid), so retry that call once; after a timed-out lease_acquire call lease_list (scope mine) first and lease_release any lease your run holds but never received, then acquire again; for any other tool read diagnostics, then retry once or report to the user.",
    "SUBPROCESS_FAILED": "Read stderr in diagnostics, fix the cause it names, then call again.",
    "ALLOCATOR_OUTPUT_INVALID": "The allocator returned no JSON envelope; report diagnostics to the user and use the Bash CLI fallback.",
    "JOB_NOT_FOUND": "Pass a job_id that a job-starting tool returned on this machine; an unknown id has no record to read.",
    "LEASE_INCOMPLETE": "The lease row lacks the build fact named in the message. A shared lease records none (the declared render server owns them): build on an ephemeral or exclusive lease instead. Otherwise the lease was acquired before the catalog declared that fact: check catalog_read for the series/profile, run /odoo-ai-agents:odoo-setup if the fact is missing there, then lease_release this lease and lease_acquire a new one.",
    "VENV_MISSING": "The lease records no venv python because the catalog row for its series/profile declares none (the venv was never built or recorded): build and record it (/odoo-ai-agents:odoo-setup; step 45-venv.sh create-venv then record-env for that series and profile, see %s), then lease_release this lease and lease_acquire again - a lease keeps the python it was acquired with." % os.path.join(
        _plugin_root(), "snippets", "venv-resolution.md"),
    "PROFILE_MISMATCH": "Omit profile when you pass lease_token: the lease is served with the catalog profile it was acquired for. To serve another profile, lease_acquire a lease for that profile.",
    "LEASE_HAS_NO_PORT": "This lease reserved no HTTP port, and serving it or running its tests binds one: lease_release it (only if you own it; otherwise ask its owner for a lease with a port) and lease_acquire again with ports 1 (2 only for prefork), then repeat the instance_serve or instance_build call with the new token.",
    "BUILD_START_FAILED": "The build could not be started (see diagnostics); fix the cause named there and call instance_build again. Nothing is running.",
    "LEASE_NOT_ADOPTED": "This parked lease is anchored to another session. If it is YOUR run's lease (lease_find with state parked and your run_id returned its token), call lease_adopt with that token and your run_id, then call instance_serve again; if it is not your run's, leave it alone and lease_acquire your own.",
    "SERVE_FAILED": "Read diagnostics.stderr: the spin-up names the cause on its `x BLOCKED:` / `x PREFLIGHT FAILED:` line. Fix that cause and call instance_serve again; nothing it started is left running.",
    "SERVER_WIDE_CORE_UNKNOWN": "The catalog declares server_wide_modules for this instance, but the series' core --load default could not be read from its Odoo checkout, so the complete set cannot be stated (it replaces Odoo's default). Nothing was started. Do not pass --load yourself: ask the user to declare the instance's odoo_root via /odoo-ai-agents:odoo-setup (catalog_read shows the row), then lease_release this lease, lease_acquire a new one and call again.",
    "ODOO_SOURCE_FACT_UNKNOWN": "The build needs an option fact Odoo declares in its own checkout (odoo/tools/config.py; openerp/ on the oldest series) - the message names it - and the lease's checkout does not state it: its odoo_root is undeclared or points at no complete Odoo checkout, and no addons_path entry leads to one. Nothing was started. Do not pass the flag yourself in extra_args: ask the user to declare the instance's odoo_root via /odoo-ai-agents:odoo-setup (catalog_read shows the row), then lease_release this lease, lease_acquire a new one and call again.",
    "I18N_EXPORT_NEEDS_DEMO": "An export must come from a database where every exported module was installed WITH its own demo data (the modules' demo records carry translatable terms too), and this one holds none - or not for the modules in diagnostics.modules_without_demo (read from the database; diagnostics.facts_source says so, or \"leases\" when it could not be read and no build recorded demo). Demo cannot be added to a database afterwards: lease_acquire a new lease, call instance_build op init demo on with languages = your target languages, job_wait it, then call instance_i18n_export on that lease.",
    "I18N_LANGUAGE_NOT_LOADED": "Every language you export (and en_US) must be loaded in this database - the message names the missing ones. Call instance_build op update on this lease with the same modules and languages including them, job_wait it until languages_loaded lists them, then call instance_i18n_export again; a language job_wait reports in languages_failed is not a code this Odoo knows.",
    "MODULE_SHADOWED": "The module named in the message exists in more than one directory of the lease's addons path (diagnostics.paths; Odoo's core addons count too). Odoo's export walks the source of every copy, so the catalog would carry the other copy's references and terms. Nothing was started. Tell the user which copies exist and ask which one is meant; the fix is a catalog addons_path that holds exactly one (/odoo-ai-agents:odoo-setup), then a new lease - never delete a copy yourself.",
    "DATABASE_BUSY": "Another job is still running on this database (diagnostics.job_id, with its op and lease): one build or export runs on a database at a time. Call job_wait with that job_id until its result is not timeout, then call this tool again - whether or not that job is yours; never release or park a lease you did not acquire to free the database.",
    "TEST_DB_HAS_DEMO": "On this series automation tests never run on a database that holds demo data, and this lease's database holds demo data (read from the database itself, or - when it cannot be read - recorded by a build on any lease of it, e.g. the one a forwarded INSTANCE_HANDLE came from; diagnostics.facts_source says which). Leave that database to its demo/acceptance use; for the tests lease_acquire a new ephemeral lease (ports 1) and call instance_build op test test_mode fresh on it - omit demo, a test build always runs with the series default (or first op init demo off, then op test test_mode reuse, again omitting demo).",
}

# Allocator codes re-worded for an agent that calls TOOLS, not the allocator CLI. Meaning and code
# stay the allocator's (scripts/lib/allocator.py ERROR_CODES); only the instruction changes.
TOOL_REMEDIES = {
    "USAGE": "Correct the argument named in the message, then call again.",
    "SERIES_REQUIRED": "Pass series (X.Y) explicitly; nothing is picked for you. catalog_read lists the declared series.",
    "ADDONS_PATH_OVERRIDE_INVALID": "Pass addons_path entries that are existing absolute directories.",
    "NO_INSTANCE_CATALOG": "No instance catalog (instances.toml) declares any instance: run /odoo-ai-agents:odoo-setup to declare the series' instance (catalog_read shows which catalog is read), then call again.",
    "NO_INSTANCE": "No catalog instance matches that series/profile: check with catalog_read, or declare one with /odoo-ai-agents:odoo-setup.",
    "EXCLUSIVE_CONFLICT": "That database is held exclusively by another lease: use mode ephemeral for an isolated database, or retry later. Never release a lease you did not acquire.",
    "PORT_POOL_EXHAUSTED": {
        "default": "Every pooled port is held (diagnostics.fields.holders names the holders): lease_release or lease_park a lease YOU acquired, then call lease_acquire again; otherwise report the holders to the user.",
        # allocator.py PORTS_BUSY_OUTSIDE_REGISTRY: diagnostics.fields.holders is EMPTY - no lease
        # holds a port of this pool, yet none can be bound (TIME_WAIT, or a process the allocator
        # does not track). Releasing or parking a lease changes nothing here.
        "reasons": {
            "ports-busy-outside-registry": "No lease holds a port of this pool (diagnostics.fields.holders is empty), yet none can be bound: the ports are held outside the lease registry (TIME_WAIT, or a process the allocator does not track). Retry shortly; if it persists, report to the user.",
        },
    },
    "ADDONS_PATH_WORKTREE_MISMATCH": "Your cwd is a different worktree of a catalog addons repo: call lease_acquire again with addons_path naming the tree you are building (normally your worktree's addons dirs).",
    "NO_CREATEDB": "The database role may not CREATE DATABASE: ask the user to grant CREATEDB, or pass no_create true if you create no database, or mode exclusive and say in your report that isolation is NOT provided.",
    "CREATEDB_UNDETERMINABLE": "CREATEDB could not be determined: run /odoo-ai-agents:odoo-setup for this series (declares python/odoo_root/db_run_mode) or start the cluster, then call again.",
    "DB_AUTH_DENIED": "Odoo cannot authenticate to Postgres: run /odoo-ai-agents:odoo-setup, or ask the user to export ODOO_PG_PASSWORD before the session starts.",
    "DB_UNREACHABLE": "The Postgres cluster did not answer: start it (or ask the user to), then call again.",
    "RUN_ID_REQUIRED": "Pass run_id: the run id you were given (INSTANCE_HANDLE.run_id, or the run_id of your own earlier lease). Never invent one; if you were given none, report NEEDS_CONTEXT(RUN_ID).",
    "RECLAIM_IN_PROGRESS": "The lease is being released or reclaimed right now by another call (lease_list shows state reclaiming): do not retry the mutation; call lease_list again in a minute - once the lease is gone it is done, and if it is still listed unchanged, report it to the user.",
    "LEASE_NOT_FOUND": "No lease has that token: call lease_list (scope mine) for the tokens this session holds.",
    "NOT_OWNER": "You did not acquire this lease (its run_id is another run's): leave it alone. Release, park or adopt only leases whose run_id is yours; a forwarded INSTANCE_HANDLE is consumed, never released.",
    "DROP_FAILED_KEPT": "The database could not be dropped, so the lease was KEPT: run /odoo-ai-agents:odoo-setup for this series (repairs the drop surface), then call lease_release again; if it still fails, report the diagnostics to the user.",
    "SHARED_NOT_PARKABLE": "A shared lease cannot be parked and needs no teardown: leave it for its readers (lease_gc reclaims it once its server is gone); lease_release it only when the user explicitly asks to stop that render server.",
    "NOT_RUNNING": "The lease is already parked (or its registry row is orphaned), so there is nothing left to park and parking again would only re-stamp its budget: to use it again call instance_serve on it (a parked lease resumes); when you are done with it, lease_release it.",
    "NOT_PARKED": "The lease is not parked: call instance_serve normally.",
    "RESUME_RACE": "Another caller already resumed this lease and its server is running: attach to that instance (instance_status) instead of launching a second one.",
    "DB_GONE": "The parked lease's database no longer exists: lease_release it, then lease_acquire and instance_build a fresh instance.",
    "WRONG_HOST": "The lease was recorded on another host: operate on it from that host, or lease_acquire your own.",
    "PID_NOT_ALIVE": "The server pid is not alive here: call instance_serve again; report to the user if it keeps failing.",
    "OWNERSHIP_UNPROVEN": "The launched server could not be proven to belong to this lease: report diagnostics to the user; do not retry blindly.",
    "NOT_FOUND": "Nothing matches: lease_acquire your own lease.",
    "NO_ANCHOR": "This server has no session anchor (server_info anchor.exported is false): tell the user; leases still work but are protected only by their server pid.",
    "UNSPECIFIED": "Read diagnostics.stderr, fix the cause it names, then call again; report to the user if unclear.",
}

# Used only for a code that is in neither table (a new allocator code this server predates).
FALLBACK_REMEDY = "Read message and diagnostics, fix the cause they name, then call again; report to the user if the cause is unclear."

_ALLOCATOR_TABLE_NAMES = ("ERROR_CODES", "ERROR_TABLE")
_lock = threading.Lock()
_allocator_cache = []  # [dict] once loaded; a list so the loader can fill it in place


def _lib_dir():
    return os.path.join(_plugin_root(), "scripts", "lib")


def _normalize_allocator_table(raw):
    """Accept {code: "remedy"} or {code: {"remedy": ..., ...}}; drop anything else."""
    out = {}
    if not isinstance(raw, dict):
        return out
    for code, val in raw.items():
        if not isinstance(code, str):
            continue
        if isinstance(val, str):
            out[code] = val
        elif isinstance(val, dict) and isinstance(val.get("remedy"), str):
            out[code] = val["remedy"]
    return out


def allocator_codes():
    """The allocator's named-code table as {code: remedy}; {} when allocator.py is absent, fails to
    import, or exposes no table. Loaded once, then cached."""
    with _lock:
        if _allocator_cache:
            return _allocator_cache[0]
        table = {}
        path = os.path.join(_lib_dir(), "allocator.py")
        if os.path.isfile(path):
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("odoo_local_allocator_codes", path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                for name in _ALLOCATOR_TABLE_NAMES:
                    if hasattr(mod, name):
                        table = _normalize_allocator_table(getattr(mod, name))
                        break
            except Exception as exc:  # a broken allocator must not take the server down
                sys.stderr.write("odoo-local: allocator error table unavailable: %s: %s\n" % (type(exc).__name__, exc))
                table = {}
        _allocator_cache.append(table)
        return table


def table():
    """The merged table {code: remedy}, where `remedy` is a plain string or a reason-split dict
    (see the module docstring and `remedy_for`): allocator remedies, overridden by their
    TOOL_REMEDIES translation, overridden by a server code (a server-code collision is logged, so
    the server's own contract for its codes can never be silently redefined)."""
    merged = dict(allocator_codes())
    merged.update(TOOL_REMEDIES)
    for code in merged:
        if code in SERVER_CODES and merged[code] != SERVER_CODES[code]:
            sys.stderr.write("odoo-local: error code %s defined by both server and allocator; server remedy kept\n" % code)
    merged.update(SERVER_CODES)
    return merged


def remedy_for(code, diagnostics=None):
    """The remedy string for `code`. When the table entry is a plain string, that string. When it
    is a `{"default": ..., "reasons": {...}}` split (see the module docstring), the `reasons` entry
    named by `diagnostics["fields"]["reason"]` when one matches, else `default` - so a caller that
    passes no diagnostics (or a reason the table does not split on) still gets a sane remedy."""
    entry = table().get(code, FALLBACK_REMEDY)
    if not isinstance(entry, dict):
        return entry
    reason = ((diagnostics or {}).get("fields") or {}).get("reason")
    reasons = entry.get("reasons") or {}
    if reason and reason in reasons:
        return reasons[reason]
    return entry.get("default", FALLBACK_REMEDY)


class ToolError(Exception):
    """Raised by a tool handler; the protocol layer turns it into an isError tool result."""

    def __init__(self, code, message, diagnostics=None):
        Exception.__init__(self, message)
        self.code = code
        self.message = message
        self.diagnostics = diagnostics if diagnostics is not None else {}

    def payload(self):
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "remedy": remedy_for(self.code, self.diagnostics),
                "diagnostics": self.diagnostics,
            }
        }


# JSON Schema of the error envelope; every tool's advertised outputSchema admits it (see protocol.py).
ERROR_ENVELOPE_SCHEMA = {
    "type": "object",
    "required": ["error"],
    "properties": {
        "error": {
            "type": "object",
            "required": ["code", "message", "remedy", "diagnostics"],
            "properties": {
                "code": {"type": "string"},
                "message": {"type": "string"},
                "remedy": {"type": "string"},
                "diagnostics": {"type": "object"},
            },
        }
    },
}
