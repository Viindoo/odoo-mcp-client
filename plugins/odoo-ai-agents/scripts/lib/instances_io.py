"""instances_io.py - read and select Odoo instance profiles from instances.toml.

The profile file uses array-of-tables form so every series key is a plain
field value (never a dotted/quoted table header):

    [[instance]]
    series = "17.0"
    profile = "minimal_17"   # optional; distinguishes two instances of the same series
    instance_key = "17.0:minimal_17"  # stable identity (<series>:<profile> or <series>)
    addons_path = ["/path/a", "/path/b"]
    run_mode = "source"
    http_port = 8069
    db_name = "odoo_17_0"
    db_host = "localhost"
    db_user = "odoo"
    db_port = 5433       # optional; ABSENT allowed -> INST_DB_PORT='' (libpq/PGPORT resolves it)
    python = ""          # optional path to a venv python
    odoo_root = ""       # optional; the checkout root that makes `import odoo` resolve
    db_run_mode = ""     # optional; native | docker | tcp-only - HOW POSTGRES IS REACHED
                         # (run_mode above describes ODOO). Vocabulary SSOT:
                         # scripts/lib/pg_mode.sh
    db_container = ""    # optional; docker mode only - the `docker exec` handle
    server_wide_modules = ["to_base"]  # optional; the DEPLOYMENT's own server-wide
                         # modules (Odoo --load) beyond the series' core default,
                         # which is read from the checkout (odoo_source_facts)
                         # and never declared here. ABSENT = none declared.

Every optional field follows the same rule as db_port: ABSENT is a REAL value and
is emitted as the empty string, never fabricated into a plausible-looking default.

Parsing uses tomllib (py3.11+) and falls back to a minimal text scan on older
Python so spin-up still works without a 3.11 interpreter. The text scan reads an
array value on one line or spread over several lines (`key = [` ... `]`). A legacy dict-of-tables
shape ([instance.X] / [instance."X"]) is tolerated on every supported Python
version: both the tomllib path and the text-scan fallback fold the trailing
header key into the item's `series`, so the two paths return the same instances.

CLI:
    python3 instances_io.py read <instances.toml> [series] [profile]
        Emit shell-eval-able KEY=VALUE lines (shlex.quote'd) for one instance.
        With no series the highest valid X.Y series is chosen. With profile set,
        further filters by profile within that series.
        Exit 1 (with an actionable message on stderr and nothing on stdout) if
        the file has no usable instance.
        On no catalog file at that path at all: exit 1 with NOTHING on stdout
        and NOTHING on stderr - a normal "nothing declared here" outcome, not
        an error.
        On a catalog file that IS present but could not be read as TOML
        (malformed syntax, a directory at that path, a permissions error,
        ...): exit 3, with exactly one diagnostic line on stderr naming the
        file and nothing on stdout. DISTINCT from exit 1 - a caller who
        declared an instance and typo'd the file must see a diagnostic
        rather than a silent miss indistinguishable from "nothing declared".
        Emitted vars include INST_PROFILE and INST_KEY in addition to the
        existing INST_* fields, and INST_SERVER_WIDE_MODULES (the declared
        server_wide_modules, comma-joined; empty when none is declared).

    python3 instances_io.py read-row <instances.toml> <series> <profile>
        Same output as `read`, for the ONE row a writer would record onto
        (select_row): an EMPTY <profile> means the UNPROFILED row of <series>,
        never "any row of the series". Exit 1 with one reason on stderr and
        nothing on stdout when the series has only profile-specific rows and
        no profile was given, or when no row matches; no catalog file at all
        is exit 1 with that reason too. Exit 3 as `read` on an unreadable file.
        A step that reads a row's facts and then records onto the same row
        uses this, so it never reads one row and writes another.

    python3 instances_io.py server-wide [--declared <a,b>] [--odoo-root <dir>]
                                        [--addons-path <dirs>]
        The server-wide module set (Odoo --load) a build or a server of this
        instance must use: Odoo's own core default read from the checkout
        (odoo_source_facts.core_server_wide_modules) followed by the declared
        set, deduplicated. The checkout is --odoo-root, else the first
        --addons-path entry (or its parent / grandparent) that holds one.
        stdout: SERVER_WIDE_MODULES=<a,b> and SERVER_WIDE_CORE=<a,b> (both
        empty when nothing is declared and the core default is unreadable:
        then no --load is passed and Odoo applies its own default).
        Exit 4 with SERVER_WIDE_CORE_UNKNOWN on stderr and nothing on stdout
        when modules ARE declared but the core default cannot be read - the
        set is never guessed, because --load REPLACES Odoo's default.

    python3 instances_io.py locate <instances.toml> <repo-path>
        Repo -> instance direction: find the [[instance]] whose addons_path
        CONTAINS <repo-path> (equal to, or a descendant of, one of its
        addons_path entries - an addons_path entry nested BELOW <repo-path>
        does NOT match). Longest matching addons_path entry wins; ties break
        to the highest series.
        On match: exit 0 and emit INST_SERIES / INST_PROFILE /
        INST_ADDONS_PATH / INST_HTTP_PORT / INST_PYTHON / INST_DB_NAME /
        INST_DB_HOST / INST_DB_USER / INST_DB_PORT.
        On no match, or no catalog file at that path at all: exit 1 with
        NOTHING on stdout and NOTHING on stderr - this is a normal, designed
        outcome (the caller falls through to the next rung of its own
        resolution ladder), never an error.
        On a catalog file that IS present but could not be read as TOML
        (malformed syntax, a directory at that path, a permissions error,
        ...): exit 3, with exactly one diagnostic line on stderr naming the
        file and nothing on stdout. DISTINCT from exit 1 - a caller who
        declared an instance and typo'd the file must see a diagnostic
        rather than a silent miss indistinguishable from "nothing declared".
"""

import re
import shlex
import sys

# SSOT for the "no declared http_port" fallback (Odoo's own stock default).
# allocator.py imports this module and points its own DEFAULT_HTTP_PORT here
# instead of repeating the literal (P5.9 8069-fallback consolidation).
DEFAULT_HTTP_PORT = 8069

# SSOT for the addons_path wire format. Odoo's --addons-path CLI flag and its
# addons_path config-file key are COMMA-separated, uniformly, across every
# indexed series 8.0-19.0 (verified via cli_help). This repo historically also
# produced a COLON-joined form in places (shell PATH convention) - that
# divergence is why the separator bug recurred. Every producer AND consumer
# of a flattened addons_path string, Python or shell, must go through
# join_addons_path()/split_addons_path() (or the shell mirror
# _addons_path_to_array() in resolve_instances.sh) instead of hand-rolling
# ",".join(...)/":".join(...)/IFS=<literal>.
#
# A catalog's DECLARED addons_path has TWO legal shapes - a native TOML array
# (canonical) and a bare flattened string (a hand-typed override) - so READING
# one off an [[instance]] item is the third member of this SSOT family,
# addons_path_list(), and never a bare item.get("addons_path", []). Handing that
# raw value straight to join_addons_path() joins a STRING character by character
# ("/a,/b" -> "/,a,/,b"): a wrong value rather than a crash, on the field that
# decides which source tree a server serves. join_addons_path() therefore stays
# strictly list -> string - a tolerant joiner would absorb exactly that mistake
# at every call site instead of leaving it findable.
ADDONS_PATH_SEP = ","


def join_addons_path(paths):
    """list[str] -> the ONE flattened wire format (comma-joined)."""
    return ADDONS_PATH_SEP.join(str(p) for p in paths)


def split_addons_path(value):
    """Flattened addons_path string -> list[str].

    Tolerates a legacy colon-joined value (an old INST_ADDONS_PATH caller, a
    hand-typed override) transparently, so a stale caller degrades gracefully
    instead of silently mis-splitting; always PRODUCE comma going forward via
    join_addons_path - this function is read-tolerant, not an invitation to
    keep emitting colon anywhere.
    """
    if not value:
        return []
    return [p.strip() for p in value.replace(":", ",").split(",") if p.strip()]


def _load_tomllib(path):
    import tomllib  # py3.11+; ImportError -> caller falls back to text scan

    with open(path, "rb") as fh:
        return tomllib.load(fh)


def _parse_value(raw):
    raw = raw.split("#", 1)[0].strip()  # drop inline comment
    if raw.startswith("[") and raw.endswith("]"):
        items = []
        for part in raw[1:-1].split(","):
            part = part.strip().strip('"').strip("'")
            if part:
                items.append(part)
        return items
    if (raw.startswith('"') and raw.endswith('"')) or (
        raw.startswith("'") and raw.endswith("'")
    ):
        return raw[1:-1]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return raw


_LEGACY_HEADER_RE = re.compile(r"^\[\s*instance\.(?P<key>.+?)\s*\]$")


def _strip_quotes(text):
    """Strip a single matching pair of surrounding single or double quotes."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _load_textscan(path):
    """Minimal fallback parser for instance tables (Python < 3.11).

    Recognizes the canonical ``[[instance]]`` array-of-tables format and the
    legacy dict-of-tables format ``[instance.<x>]`` / ``[instance."<x>"]``. For
    a legacy header the trailing key segment (with surrounding quotes stripped)
    is folded into the item as its ``series``. This mirrors the ``tomllib`` path
    so a legacy file yields the same instances on Python 3.10 and 3.11+.
    """
    instances = []
    cur = None
    pending = None  # (key, text so far) while a multi-line array value is open
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if pending is not None:
                # Inside `key = [` ... `]`: collect element lines (comments dropped)
                # until the closing bracket, then parse the joined value once.
                key, acc = pending
                body = line.split("#", 1)[0].strip()
                acc = acc + " " + body
                if "]" in body:
                    pending = None
                    if cur is not None:
                        cur[key] = _parse_value(acc)
                else:
                    pending = (key, acc)
                continue
            if not line or line.startswith("#"):
                continue
            if line == "[[instance]]":
                cur = {}
                instances.append(cur)
                continue
            legacy = _LEGACY_HEADER_RE.match(line)
            if legacy:
                cur = {"series": _strip_quotes(legacy.group("key"))}
                instances.append(cur)
                continue
            if line.startswith("["):
                # Any other table/array header ends the current instance scope.
                cur = None
                continue
            if cur is None or "=" not in line:
                continue
            key, _, val = line.partition("=")
            head = val.split("#", 1)[0].strip()
            if head.startswith("[") and "]" not in head:
                pending = (key.strip(), head)
                continue
            cur[key.strip()] = _parse_value(val)
    return {"instance": instances}


def load_instances(path):
    """Return a list of instance dicts from the profile file.

    Tolerates: array-of-tables (current), legacy dict-of-tables ([instance.X]),
    and Python < 3.11 via the text-scan fallback.
    """
    try:
        data = _load_tomllib(path)
    except ImportError:
        data = _load_textscan(path)

    items = data.get("instance")
    if isinstance(items, dict):
        # Legacy [instance.X] shape: dict keyed by version.
        norm = []
        for key, val in items.items():
            if isinstance(val, dict):
                val = dict(val)
                val.setdefault("series", val.get("version", key))
                norm.append(val)
        items = norm
    if not isinstance(items, list):
        return []
    return [it for it in items if isinstance(it, dict)]


def series_of(item):
    return str(item.get("series", item.get("version", "")))


def profile_of(item):
    return str(item.get("profile", ""))


def instance_key_of(item):
    """Stable identity: '<series>:<profile>' when profiled, else '<series>'."""
    prof = profile_of(item)
    series = series_of(item)
    return f"{series}:{prof}" if prof else series


def _series_key(series):
    m = re.match(r"^(\d+)\.(\d+)$", series)
    return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)


def select_instance(items, want=None, profile=None):
    """Pick one instance. With ``want`` set, match by series exactly.
    With ``profile`` set, further filter by profile within that series.
    Otherwise return the highest valid X.Y series (placeholders skipped).

    Returns ``(item, defaulted)`` where ``defaulted`` is True when the choice
    was made by the highest-series rule. Returns ``(None, False)`` if none match
    -- including the case where ``want`` is None but no item carries a valid
    ``X.Y`` series (no garbage/placeholder fallback).
    """
    if not items:
        return None, False
    if want:
        for it in items:
            if series_of(it) == want:
                if profile is None or profile_of(it) == profile:
                    return it, False
        return None, False
    # No series filter: pick highest valid X.Y, optionally filtered by profile.
    candidates = items if profile is None else [it for it in items if profile_of(it) == profile]
    valid = [it for it in candidates if _series_key(series_of(it)) != (-1, -1)]
    if not valid:
        return None, False
    chosen = max(valid, key=lambda it: _series_key(series_of(it)))
    return chosen, True


def select_row(items, series, profile=""):
    """The ONE row of (``series``, ``profile``) a writer records onto.

    An empty ``profile`` selects the UNPROFILED row - never "any row of the
    series" (that is select_instance's lenient reading). Returns ``(row, None)``
    on a match, else ``(None, reason)`` where reason says why: the series has
    only profile-specific rows and no profile was given, or no row matches.
    config_merge.py toml-upsert-instance-keys applies the same rule.
    """
    same = [it for it in items or [] if series_of(it) == series]
    rows = [it for it in same if profile_of(it) == (profile or "")]
    if rows:
        return rows[0], None
    if not profile and same:
        return None, ("series %s has only profile-specific [[instance]] rows but no "
                      "--profile was given - pass --profile <name>" % series)
    label = "%s:%s" % (series, profile) if profile else series
    return None, "no [[instance]] row %s is declared - declare it first (step 40)" % label


def addons_path_list(item):
    """Normalize one item's addons_path to list[str], whichever shape it
    parsed as: a native TOML array (the canonical form) or a bare/flattened
    string (a hand-typed override, e.g. "/a,/b"). Reuses split_addons_path
    for the string case instead of a second, hand-rolled splitter - the SSOT
    the module docstring requires.

    PUBLIC because it is the only sanctioned way to read a declared
    addons_path: every caller outside this module that wants the entries, or
    wants them flattened via join_addons_path(), must come through here (see
    the ADDONS_PATH_SEP block above for why the raw value must never reach the
    joiner)."""
    value = item.get("addons_path", [])
    if isinstance(value, list):
        return [str(p) for p in value]
    return split_addons_path(str(value))


# Odoo's --load flag and its server_wide_modules conf key take a COMMA-separated
# MODULE list (odoo/tools/config.py on every series). The same character as
# ADDONS_PATH_SEP, but a different fact (module names, not directories), so it
# carries its own name.
MODULE_LIST_SEP = ","


def split_module_list(value):
    """A module list in either shape - a list, or a flattened comma string -
    as list[str]: entries stripped, empties dropped, order kept."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        items = [str(v) for v in value]
    else:
        items = str(value).split(MODULE_LIST_SEP)
    return [m.strip() for m in items if m.strip()]


def server_wide_modules_of(item):
    """The server_wide_modules a catalog row DECLARES (a TOML array; a
    hand-typed comma string is tolerated), as list[str]. [] when absent: the
    row declares none, which is a real value, not an unknown."""
    return split_module_list(item.get("server_wide_modules", []))


class ServerWideCoreUnknown(Exception):
    """Modules are declared server-wide, but Odoo's own core default cannot be
    read from the checkout - so the full --load set cannot be stated."""


_SOURCE_FACTS = []  # [module or None] once loaded


def _source_facts():
    """scripts/lib/odoo_source_facts.py, loaded by path (this module is also
    loaded by path, so its directory is not necessarily on sys.path); None
    when it cannot be loaded. Loaded once."""
    if not _SOURCE_FACTS:
        _SOURCE_FACTS.append(_load_source_facts())
    return _SOURCE_FACTS[0]


def _load_source_facts():
    import importlib.util
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odoo_source_facts.py")
    try:
        spec = importlib.util.spec_from_file_location("odoo_source_facts", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except (OSError, ImportError, SyntaxError):
        return None
    return mod


def core_server_wide_default(odoo_root, addons_paths=None):
    """Odoo's own default server-wide set for this instance's checkout, read
    from source; None when it cannot be read. The checkout is the one
    odoo_source_facts.locate_odoo_root picks (the declared odoo_root, else the
    first addons_path entry, parent or grandparent holding Odoo) - one locator,
    so the checkout read here is the one every other reader and the launcher use."""
    facts = _source_facts()
    if facts is None:
        return None
    root = facts.locate_odoo_root(odoo_root, addons_paths)
    if root is None:
        return None
    mods = facts.core_server_wide_modules(root)
    return list(mods) if mods is not None else None


def effective_server_wide_modules(declared, odoo_root, addons_paths=None):
    """The --load set a build or a server of this instance must use:
    (effective, core). effective = core default + declared, deduplicated, core
    first. ([], core-or-None) when nothing is declared - no --load is passed
    and Odoo applies its own default, which is already correct. Raises
    ServerWideCoreUnknown when modules are declared but the core default is
    unreadable: --load REPLACES Odoo's default, so a set without the core
    modules would drop them, and the core set is never guessed."""
    declared = split_module_list(declared)
    core = core_server_wide_default(odoo_root, addons_paths)
    if not declared:
        return [], core
    if core is None:
        raise ServerWideCoreUnknown(
            "server_wide_modules declares %s, but Odoo's core --load default could not be read "
            "from the checkout (odoo_root %r)" % (MODULE_LIST_SEP.join(declared), odoo_root or ""))
    out = []
    for m in core + declared:
        if m not in out:
            out.append(m)
    return out, core


def _rstrip_slashes_locate(path):
    """Strip ALL trailing '/' from path (mirrors resolve_instances.sh's
    _odoo_ai_home_rstrip_slashes), so a declared addons_path with a stray
    trailing slash still matches. An all-slashes input reduces to '/'."""
    s = str(path)
    while s.endswith("/") and s != "/":
        s = s[:-1]
    return s or "/"


def find_covering_instance(items, repo_path):
    """Return the [[instance]] item whose addons_path CONTAINS repo_path, or
    None if none does.

    "Contains" means repo_path is EQUAL TO, or a DESCENDANT of, one of the
    item's addons_path entries. An addons_path entry that is itself nested
    BELOW repo_path (repo_path is an ANCESTOR of the declared entry) does
    NOT match - only descendant-or-equal counts, by design: the repo must be
    covered BY the declared root, not merely contain it.

    Longest matching addons_path entry wins (most specific declaration);
    ties break to the highest valid series.
    """
    repo_norm = _rstrip_slashes_locate(repo_path)
    best = None
    best_len = -1
    best_series_key = None
    for item in items:
        for raw in addons_path_list(item):
            root_norm = _rstrip_slashes_locate(raw)
            if repo_norm != root_norm and not repo_norm.startswith(root_norm + "/"):
                continue
            length = len(root_norm)
            series_key = _series_key(series_of(item))
            if length > best_len or (length == best_len and series_key > best_series_key):
                best = item
                best_len = length
                best_series_key = series_key
    return best


def _emit(name, value):
    if isinstance(value, list):
        value = join_addons_path(value)
    print(f"{name}={shlex.quote(str(value))}")


def _cmd_read(argv):
    if len(argv) < 1:
        sys.stderr.write("Usage: instances_io.py read <instances.toml> [series] [profile]\n")
        return 2
    path = argv[0]
    want = argv[1] if len(argv) > 1 and argv[1] else ""
    prof = argv[2] if len(argv) > 2 and argv[2] else None
    try:
        items = load_instances(path)
    except FileNotFoundError:
        # No catalog file at all is a normal "nothing declared here" miss,
        # not an error - the caller (50-instance-spinup.sh) treats a
        # non-zero exit plus empty stdout as "nothing to spin up" and reports
        # its own guidance. No stderr noise here.
        return 1
    except (OSError, ValueError) as exc:
        # The catalog file IS present (a directory at that path, a
        # permissions error, malformed TOML syntax, ...) but could not be
        # read as an instance catalog. DISTINCT from a genuine miss: a
        # caller who declared an instance and typo'd the file must see a
        # diagnostic rather than a silent miss indistinguishable from
        # "nothing declared". A bug inside load_instances that raises
        # anything else (e.g. AttributeError, TypeError) is NOT caught here
        # and propagates.
        sys.stderr.write(
            f"instances_io.py: {path} exists but could not be read as a TOML "
            f"instance catalog: {exc}\n"
        )
        return 3
    tbl, defaulted = select_instance(items, want or None, profile=prof)
    if tbl is None:
        sys.stderr.write(
            f"No valid Odoo instance found in {path}. "
            "Run the setup step that writes [[instance]] entries, or edit the "
            "file to add a valid series like 17.0.\n"
        )
        return 1
    if defaulted:
        sys.stderr.write(
            f"Selected instance series {series_of(tbl)} (highest); "
            "use --version to override.\n"
        )
    _emit_row(tbl)
    return 0


def _cmd_read_row(argv):
    if len(argv) != 3:
        sys.stderr.write("Usage: instances_io.py read-row <instances.toml> <series> <profile>\n")
        return 2
    path, series, profile = argv
    try:
        items = load_instances(path)
    except FileNotFoundError:
        sys.stderr.write(f"x no instance catalog at {path} - declare the instance first (step 40).\n")
        return 1
    except (OSError, ValueError) as exc:
        sys.stderr.write(
            f"instances_io.py: {path} exists but could not be read as a TOML "
            f"instance catalog: {exc}\n"
        )
        return 3
    tbl, reason = select_row(items, series, profile)
    if tbl is None:
        sys.stderr.write(f"x {reason}.\n")
        return 1
    _emit_row(tbl)
    return 0


def _emit_row(tbl):
    _emit("INST_SERIES", series_of(tbl))
    _emit("INST_ADDONS_PATH", tbl.get("addons_path", []))
    _emit("INST_RUN_MODE", tbl.get("run_mode", "source"))
    _emit("INST_HTTP_PORT", tbl.get("http_port", DEFAULT_HTTP_PORT))
    _emit("INST_DB_NAME", tbl.get("db_name", "odoo"))
    _emit("INST_DB_HOST", tbl.get("db_host", "localhost"))
    _emit("INST_DB_USER", tbl.get("db_user", "odoo"))
    # db_port is EMPTY when undeclared (never a fabricated 5432): an empty value
    # tells consumers to omit the flag and let libpq/PGPORT resolve the port.
    _emit("INST_DB_PORT", tbl.get("db_port", ""))
    _emit("INST_PYTHON", tbl.get("python", ""))
    # Environment facts recorded by 45-venv.sh, all three empty when undeclared
    # (a catalog written before they existed is valid and MUST NOT be guessed at):
    # odoo_root makes `import odoo` resolve for a source checkout; db_run_mode +
    # db_container say how a libpq CLIENT BINARY reaches this cluster, and are
    # consulted ONLY by client-binary consumers - never by the CREATEDB capability
    # check, which asks the cluster itself.
    _emit("INST_ODOO_ROOT", tbl.get("odoo_root", ""))
    _emit("INST_DB_RUN_MODE", tbl.get("db_run_mode", ""))
    _emit("INST_DB_CONTAINER", tbl.get("db_container", ""))
    _emit("INST_PROFILE", profile_of(tbl))
    _emit("INST_KEY", instance_key_of(tbl))
    # The DEPLOYMENT's declared server-wide modules only (empty = none); the
    # core default is added by `server-wide`, never stored in the catalog.
    _emit("INST_SERVER_WIDE_MODULES", MODULE_LIST_SEP.join(server_wide_modules_of(tbl)))


def _cmd_server_wide(argv):
    flags = {"--declared": "", "--odoo-root": "", "--addons-path": ""}
    i = 0
    while i < len(argv):
        if argv[i] in flags and i + 1 < len(argv):
            flags[argv[i]] = argv[i + 1]
            i += 2
            continue
        sys.stderr.write("Usage: instances_io.py server-wide [--declared <a,b>] "
                         "[--odoo-root <dir>] [--addons-path <dirs>]\n")
        return 2
    try:
        effective, core = effective_server_wide_modules(
            flags["--declared"], flags["--odoo-root"], split_addons_path(flags["--addons-path"]))
    except ServerWideCoreUnknown as exc:
        sys.stderr.write("SERVER_WIDE_CORE_UNKNOWN: %s\n" % exc)
        return 4
    print("SERVER_WIDE_MODULES=%s" % shlex.quote(MODULE_LIST_SEP.join(effective)))
    print("SERVER_WIDE_CORE=%s" % shlex.quote(MODULE_LIST_SEP.join(core or [])))
    return 0


def _cmd_locate(argv):
    if len(argv) < 2:
        sys.stderr.write("Usage: instances_io.py locate <instances.toml> <repo-path>\n")
        return 2
    path, repo_path = argv[0], argv[1]
    try:
        items = load_instances(path)
    except FileNotFoundError:
        # No catalog file at all is, for this subcommand, indistinguishable
        # from "no declared instance covers this repo" - a normal ladder
        # miss, not an error. No stderr noise; the caller falls to its next
        # rung.
        return 1
    except (OSError, ValueError) as exc:
        # The catalog file IS present (a directory at that path, a
        # permissions error, malformed TOML syntax, ...) but could not be
        # read as an instance catalog. DISTINCT from a genuine miss: a
        # caller who declared an instance and typo'd the file gets a
        # diagnostic instead of silence indistinguishable from "nothing
        # declared". A bug inside load_instances that raises anything else
        # (e.g. AttributeError, TypeError) is NOT caught here and propagates.
        sys.stderr.write(
            f"instances_io.py: {path} exists but could not be read as a TOML "
            f"instance catalog: {exc}\n"
        )
        return 3
    tbl = find_covering_instance(items, repo_path)
    if tbl is None:
        # DESIGNED outcome, not an error: nothing on stdout, nothing on
        # stderr. Do not raise, do not print a traceback, do not warn.
        return 1
    _emit("INST_SERIES", series_of(tbl))
    _emit("INST_PROFILE", profile_of(tbl))
    _emit("INST_ADDONS_PATH", tbl.get("addons_path", []))
    _emit("INST_HTTP_PORT", tbl.get("http_port", DEFAULT_HTTP_PORT))
    _emit("INST_PYTHON", tbl.get("python", ""))
    _emit("INST_DB_NAME", tbl.get("db_name", "odoo"))
    _emit("INST_DB_HOST", tbl.get("db_host", "localhost"))
    _emit("INST_DB_USER", tbl.get("db_user", "odoo"))
    # db_port is EMPTY when undeclared (never a fabricated 5432): an empty
    # value tells consumers to omit the flag and let libpq/PGPORT resolve it.
    _emit("INST_DB_PORT", tbl.get("db_port", ""))
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "read":
        return _cmd_read(argv[1:])
    if argv[0] == "read-row":
        return _cmd_read_row(argv[1:])
    if argv[0] == "locate":
        return _cmd_locate(argv[1:])
    if argv[0] == "server-wide":
        return _cmd_server_wide(argv[1:])
    sys.stderr.write(f"Unknown subcommand: {argv[0]!r}. Use 'read', 'read-row', 'locate' or 'server-wide'.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
