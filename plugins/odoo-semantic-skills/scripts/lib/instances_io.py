"""instances_io.py - read and select Odoo instance profiles from instances.toml.

The profile file uses array-of-tables form so every series key is a plain
field value (never a dotted/quoted table header):

    [[instance]]
    series = "17.0"
    addons_path = ["/path/a", "/path/b"]
    run_mode = "source"
    http_port = 8069
    db_name = "odoo_17_0"
    db_host = "localhost"
    db_user = "odoo"
    python = ""          # optional path to a venv python

Parsing uses tomllib (py3.11+) and falls back to a minimal text scan on older
Python so spin-up still works without a 3.11 interpreter. A legacy dict-of-tables
shape ([instance.X] / [instance."X"]) is tolerated on every supported Python
version: both the tomllib path and the text-scan fallback fold the trailing
header key into the item's `series`, so the two paths return the same instances.

CLI:
    python3 instances_io.py read <instances.toml> [series]
        Emit shell-eval-able KEY=VALUE lines (shlex.quote'd) for one instance.
        With no series the highest valid X.Y series is chosen.
        Exit 1 (with an actionable message on stderr and nothing on stdout) if
        the file has no usable instance.
"""

import re
import shlex
import sys


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


def _series_key(series):
    m = re.match(r"^(\d+)\.(\d+)$", series)
    return (int(m.group(1)), int(m.group(2))) if m else (-1, -1)


def select_instance(items, want=None):
    """Pick one instance. With ``want`` set, match by series exactly.
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
                return it, False
        return None, False
    valid = [it for it in items if _series_key(series_of(it)) != (-1, -1)]
    if not valid:
        return None, False
    chosen = max(valid, key=lambda it: _series_key(series_of(it)))
    return chosen, True


def _emit(name, value):
    if isinstance(value, list):
        value = ":".join(str(x) for x in value)
    print(f"{name}={shlex.quote(str(value))}")


def _cmd_read(argv):
    if len(argv) < 1:
        sys.stderr.write("Usage: instances_io.py read <instances.toml> [series]\n")
        return 2
    path = argv[0]
    want = argv[1] if len(argv) > 1 and argv[1] else ""
    try:
        items = load_instances(path)
    except Exception:
        return 1
    tbl, defaulted = select_instance(items, want or None)
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
    _emit("INST_VERSION", series_of(tbl))
    _emit("INST_ADDONS_PATH", tbl.get("addons_path", []))
    _emit("INST_RUN_MODE", tbl.get("run_mode", "source"))
    _emit("INST_HTTP_PORT", tbl.get("http_port", 8069))
    _emit("INST_DB_NAME", tbl.get("db_name", "odoo"))
    _emit("INST_DB_HOST", tbl.get("db_host", "localhost"))
    _emit("INST_DB_USER", tbl.get("db_user", "odoo"))
    _emit("INST_PYTHON", tbl.get("python", ""))
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "read":
        return _cmd_read(argv[1:])
    sys.stderr.write(f"Unknown subcommand: {argv[0]!r}. Use 'read'.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
