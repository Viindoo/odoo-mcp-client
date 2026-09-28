"""tools_catalog.py - read-only lookup tools: the local instance catalog, series detection, and
project state dirs.

Each tool calls the scripts/lib function that already owns the rule, in-process:
  catalog_read / catalog_locate -> instances_io.load_instances / find_covering_instance
  series_detect                 -> odoo_series.detect
  project_dir                   -> paths.share_dir / paths.isolate_dir
The one exception is WHICH catalog file to read: that ladder is owned by
scripts/lib/resolve_instances.sh (`--path`), so it is asked, never re-implemented here.
"""

import datetime
import os

from . import cli
from .errors import ToolError

RESOLVE_INSTANCES = "scripts/lib/resolve_instances.sh"
_RESOLVE_TIMEOUT_S = 15

_CWD_PROP = {
    "type": "string",
    "minLength": 1,
    "description": "Absolute directory whose .odoo-ai/instances.toml is the transitional project "
                   "fallback, consulted only when no machine-global catalog declares an instance. "
                   "Omit to use the server's working directory.",
}

# One catalog row. Normalized keys are always present; every other declared key passes through
# as declared, and an optional key the catalog does not declare is ABSENT (never defaulted).
ROW_SCHEMA = {
    "type": "object",
    "required": ["series", "profile", "instance_key", "addons_path", "server_wide_modules"],
    "properties": {
        "series": {"type": "string"},
        "profile": {"type": "string"},
        "instance_key": {"type": "string"},
        "addons_path": {"type": "array", "items": {"type": "string"}},
        "server_wide_modules": {"type": "array", "items": {"type": "string"},
                                "description": "Server-wide modules (Odoo --load) this deployment "
                                               "declares beyond the series' core default, which is "
                                               "read from the checkout and not listed here; empty = "
                                               "none declared. instance_build and instance_serve "
                                               "load core + these; change them only through "
                                               "/odoo-ai-agents:odoo-setup."},
        # Passed through as declared (untyped here: a hand-edited catalog may spell them loosely).
        "http_port": {"description": "Declared HTTP port."},
        "db_name": {"description": "Declared database name."},
        "db_host": {"description": "Declared Postgres host."},
        "db_user": {"description": "Declared Postgres role."},
        "db_port": {"description": "Declared Postgres port; absent means libpq/PGPORT decides."},
        "python": {"description": "Declared interpreter for this instance."},
        "odoo_root": {"description": "Declared checkout root that makes `import odoo` resolve."},
        "run_mode": {"description": "How Odoo runs, as declared."},
        "db_run_mode": {"description": "How Postgres is reached, as declared (vocabulary owned by scripts/lib/pg_mode.sh)."},
        "db_container": {"description": "docker db_run_mode only: the container handle."},
    },
}


def _jsonable(value):
    """TOML can carry dates/times; JSON cannot. Everything else is already JSON-shaped."""
    if isinstance(value, (datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


def _row(io, item):
    row = _jsonable(dict(item))
    row["series"] = io.series_of(item)
    row["profile"] = io.profile_of(item)
    row["instance_key"] = io.instance_key_of(item)
    row["addons_path"] = io.addons_path_list(item)
    row["server_wide_modules"] = io.server_wide_modules_of(item)
    return row


def _resolve_catalog_path(cwd):
    workdir = cwd or os.getcwd()
    if not os.path.isdir(workdir):
        raise ToolError("PATH_NOT_DIRECTORY", "cwd is not a directory: %s" % workdir, {"cwd": workdir})
    try:
        rc, out, err = cli.run_plugin_script(RESOLVE_INSTANCES, ["--path"], workdir, _RESOLVE_TIMEOUT_S)
    except cli.SubprocessTimeout as exc:
        raise ToolError("SUBPROCESS_TIMEOUT", "resolve_instances.sh --path exceeded %ss" % exc.timeout_s,
                        {"stderr": cli.tail(exc.stderr)})
    path = out.strip().splitlines()[-1].strip() if out.strip() else ""
    if rc != 0 or not path:
        raise ToolError("SUBPROCESS_FAILED", "resolve_instances.sh --path failed (rc=%d): %s" % (rc, err.strip()),
                        {"rc": rc, "stderr": cli.tail(err)})
    return path


def _load(io, path):
    """(items, exists). A missing file is a normal empty catalog; an unreadable one is an error."""
    try:
        return io.load_instances(path), True
    except FileNotFoundError:
        return [], False
    except (OSError, ValueError) as exc:
        raise ToolError("CATALOG_UNREADABLE", "%s exists but could not be read as a TOML instance catalog: %s" % (path, exc),
                        {"catalog_path": path, "exception": type(exc).__name__})


def _abs_path_arg(args, key):
    value = args[key]
    if not os.path.isabs(value):
        raise ToolError("INVALID_ARGUMENTS", "arguments.%s: must be an absolute path, got %r" % (key, value))
    return value


# --------------------------------------------------------------------------- #
# handlers
# --------------------------------------------------------------------------- #
def catalog_read(args, ctx):
    io = cli.load_lib("instances_io")
    if args.get("cwd"):
        _abs_path_arg(args, "cwd")
    path = _resolve_catalog_path(args.get("cwd"))
    items, exists = _load(io, path)
    series = args.get("series")
    profile = args.get("profile")
    rows = []
    for item in items:
        if series is not None and io.series_of(item) != series:
            continue
        if profile is not None and io.profile_of(item) != profile:
            continue
        rows.append(_row(io, item))
    return {"catalog_path": path, "catalog_exists": exists, "rows": rows}


def catalog_locate(args, ctx):
    io = cli.load_lib("instances_io")
    repo_path = _abs_path_arg(args, "path")
    if args.get("cwd"):
        _abs_path_arg(args, "cwd")
    catalog = _resolve_catalog_path(args.get("cwd"))
    items, exists = _load(io, catalog)
    item = io.find_covering_instance(items, repo_path)
    return {
        "catalog_path": catalog,
        "catalog_exists": exists,
        "matched": item is not None,
        "row": _row(io, item) if item is not None else None,
    }


def series_detect(args, ctx):
    series_mod = cli.load_lib("odoo_series")
    root = _abs_path_arg(args, "path")
    if not os.path.isdir(root):
        raise ToolError("PATH_NOT_DIRECTORY", "path is not a directory: %s" % root, {"path": root})
    result = series_mod.detect(root)
    out = {"path": root}
    for key in ("status", "series", "step", "era", "evidence", "hint"):
        out[key] = str(result.get(key, ""))
    return out


def project_dir(args, ctx):
    paths_mod = cli.load_lib("paths")
    cwd = _abs_path_arg(args, "cwd")
    if not os.path.isdir(cwd):
        raise ToolError("PATH_NOT_DIRECTORY", "cwd is not a directory: %s" % cwd, {"cwd": cwd})
    resolve = paths_mod.share_dir if args["axis"] == "share" else paths_mod.isolate_dir
    try:
        path = resolve(cwd)
    except paths_mod.ProjectDirError as exc:
        raise ToolError("PROJECT_DIR_UNRESOLVED", str(exc), {"cwd": cwd, "axis": args["axis"]})
    return {"axis": args["axis"], "cwd": cwd, "path": path}


# --------------------------------------------------------------------------- #
# schemas + registration
# --------------------------------------------------------------------------- #
CATALOG_READ_INPUT = {
    "type": "object",
    "properties": {
        "series": {"type": "string", "minLength": 1,
                   "description": "Keep only rows whose series equals this exact string (X.Y form, as the catalog declares it)."},
        "profile": {"type": "string",
                    "description": "Keep only rows whose profile equals this exact string; \"\" selects unprofiled rows."},
        "cwd": _CWD_PROP,
    },
    "additionalProperties": False,
}
CATALOG_READ_OUTPUT = {
    "type": "object",
    "required": ["catalog_path", "catalog_exists", "rows"],
    "properties": {
        "catalog_path": {"type": "string"},
        "catalog_exists": {"type": "boolean"},
        "rows": {"type": "array", "items": ROW_SCHEMA},
    },
}

CATALOG_LOCATE_INPUT = {
    "type": "object",
    "required": ["path"],
    "properties": {
        "path": {"type": "string", "minLength": 1,
                 "description": "Absolute path of the repository or worktree to map to a declared instance."},
        "cwd": _CWD_PROP,
    },
    "additionalProperties": False,
}
CATALOG_LOCATE_OUTPUT = {
    "type": "object",
    "required": ["catalog_path", "catalog_exists", "matched", "row"],
    "properties": {
        "catalog_path": {"type": "string"},
        "catalog_exists": {"type": "boolean"},
        "matched": {"type": "boolean"},
        "row": {"anyOf": [ROW_SCHEMA, {"type": "null"}]},
    },
}

SERIES_DETECT_INPUT = {
    "type": "object",
    "required": ["path"],
    "properties": {
        "path": {"type": "string", "minLength": 1,
                 "description": "Absolute path of the Odoo checkout or addons repository root to inspect."},
    },
    "additionalProperties": False,
}
SERIES_DETECT_OUTPUT = {
    "type": "object",
    "required": ["path", "status", "series", "step", "era", "evidence", "hint"],
    "properties": {
        "path": {"type": "string"},
        "status": {"type": "string", "enum": ["OK", "NEEDS_CONTEXT"]},
        "series": {"type": "string"},
        "step": {"type": "string", "enum": ["", "1", "2", "3", "4", "5"]},
        "era": {"type": "string"},
        "evidence": {"type": "string"},
        "hint": {"type": "string"},
    },
}

PROJECT_DIR_INPUT = {
    "type": "object",
    "required": ["cwd", "axis"],
    "properties": {
        "cwd": {"type": "string", "minLength": 1,
                "description": "Absolute directory inside the project (repo, worktree, or module tree) to resolve for."},
        "axis": {"type": "string", "enum": ["share", "isolate"],
                 "description": "share: one dir for every worktree of the repo. isolate: a dir private to cwd's worktree."},
    },
    "additionalProperties": False,
}
PROJECT_DIR_OUTPUT = {
    "type": "object",
    "required": ["axis", "cwd", "path"],
    "properties": {
        "axis": {"type": "string", "enum": ["share", "isolate"]},
        "cwd": {"type": "string"},
        "path": {"type": "string"},
    },
}


def register(registry, ctx):
    registry.add(
        "catalog_read",
        "Read this machine's Odoo instance catalog (instances.toml) and return EVERY declared "
        "instance row: series, profile, instance_key, addons_path (list), server_wide_modules (list; "
        "the deployment's own --load modules, empty = none), plus the declared python, "
        "odoo_root, db_* and port fields. Call it to learn which series/profiles exist locally before "
        "leasing or building. Filters are exact matches; with no filter all rows come back - it never "
        "picks one for you. catalog_path names the file actually read; catalog_exists=false with no "
        "rows means nothing is declared (run /odoo-ai-agents:odoo-setup). An optional field the "
        "catalog does not declare is absent, never defaulted. Declarations only, not live process state.",
        CATALOG_READ_INPUT, CATALOG_READ_OUTPUT, catalog_read,
        title="Read local instance catalog", read_only=True,
    )
    registry.add(
        "catalog_locate",
        "Map a repository path to the declared instance whose addons_path covers it (path equal to, "
        "or inside, one addons_path entry; an entry nested below path does not count). The longest "
        "matching entry wins; ties go to the highest series. matched=false with row=null is a normal "
        "miss, not an error. path must be absolute and is compared as given (no symlink resolution). "
        "Call it to find which declared instance serves the repo or worktree you are working in.",
        CATALOG_LOCATE_INPUT, CATALOG_LOCATE_OUTPUT, catalog_locate,
        title="Locate instance for a repo", read_only=True,
    )
    registry.add(
        "series_detect",
        "Derive the Odoo major series of a checkout on disk, strongest evidence first (core "
        "release.py, then a series-named git branch). status=OK: series is resolved (step 1 or 2) "
        "and evidence cites the file or branch. status=NEEDS_CONTEXT: series is EMPTY and must not be "
        "guessed - step 3 puts an unconfirmed manifest candidate in hint, step 4 gives only an era "
        "range, step 5 lists hint files, empty step means no evidence; confirm with the user or the "
        "task. Edition (Community/Enterprise) is not detectable here. Call it before choosing a "
        "series for an unfamiliar checkout.",
        SERIES_DETECT_INPUT, SERIES_DETECT_OUTPUT, series_detect,
        title="Detect Odoo series of a checkout", read_only=True,
    )
    registry.add(
        "project_dir",
        "Return this project's machine-global state directory under $ODOO_AI_HOME/projects/, "
        "creating it if absent. axis=share: one dir shared by every worktree of the repo containing "
        "cwd; axis=isolate: a dir private to cwd's worktree. Pick the axis the artifact's state "
        "classification names. Write .odoo-ai artifacts to the returned path, never to a "
        "cwd-relative .odoo-ai/. Honors ODOO_AI_PROJECT_DIR / ODOO_AI_WORKTREE_DIR overrides. "
        "PROJECT_DIR_UNRESOLVED outside git when no project marker exists above cwd.",
        PROJECT_DIR_INPUT, PROJECT_DIR_OUTPUT, project_dir,
        title="Resolve project state dir", read_only=False, destructive=False, idempotent=True,
    )
