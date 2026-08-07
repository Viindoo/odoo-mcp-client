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

Parsing uses tomllib (py3.11+) and falls back to a minimal text scan on older
Python so spin-up still works without a 3.11 interpreter. A legacy dict-of-tables
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
        existing INST_* fields.

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
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
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


def _addons_path_list(item):
    """Normalize one item's addons_path to list[str], whichever shape it
    parsed as: a native TOML array (the canonical form) or a bare/flattened
    string (a hand-typed override, e.g. "/a,/b"). Reuses split_addons_path
    for the string case instead of a second, hand-rolled splitter - the SSOT
    the module docstring requires."""
    value = item.get("addons_path", [])
    if isinstance(value, list):
        return [str(p) for p in value]
    return split_addons_path(str(value))


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
        for raw in _addons_path_list(item):
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
    _emit("INST_PROFILE", profile_of(tbl))
    _emit("INST_KEY", instance_key_of(tbl))
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
    if argv[0] == "locate":
        return _cmd_locate(argv[1:])
    sys.stderr.write(f"Unknown subcommand: {argv[0]!r}. Use 'read' or 'locate'.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
