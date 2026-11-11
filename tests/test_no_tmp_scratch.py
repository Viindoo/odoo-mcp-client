"""Guard: the plugin's CODE (scripts, hooks, Python) writes nothing to the ambient temp dir.

`/tmp` is wiped on reboot, shared by every user and project on the host, and not namespaced per
worktree, so an artifact written there is both losable and un-attributable (and on a memory-backed
temp dir, a leak exhausts it for every session). The one sanctioned scratch destination is the
state root (`odoo_ai_state_root`, `odoo_ai_scratch_dir` in scripts/lib/state_reclaim.sh). Scans
every `.sh` and `.py` file under `plugins/` - never instruction prose - for:

  Rule 1 - `TMPDIR` appears nowhere (zero tolerance, no allowlist).
  Rule 2 - every `/tmp` or `/var/tmp` is the state-root fallback `${HOME:-/tmp}` (a path
           resolution that writes nothing) or a reasoned `TMP_ALLOWLIST` entry.
  Rule 3 - no ambient temp dir reached without naming it: a `mktemp` with no destination,
           `tempfile.mkstemp/mkdtemp/gettempdir/...`, `--basetemp`, `TMP=` / `TEMP=`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"
_SKIP_DIR_PARTS = {"__pycache__", ".git", "node_modules", ".pytest_cache"}
_CODE_SUFFIXES = {".sh", ".py"}

TMPDIR_RE = re.compile(r"TMPDIR")
# `(?![A-Za-z0-9_])` stops `/tmpfs`; `/var/tmp` is folded in as the obvious workaround.
TMP_PATH_RE = re.compile(r"/(?:var/)?tmp(?![A-Za-z0-9_])")
STATE_ROOT_FALLBACK_PREFIX = "${HOME:-"
# `mktemp` followed only by option flags / redirections: anything that names a destination
# (`-p DIR` or a TEMPLATE argument) stops matching, because naming one is what the rule asks.
AMBIENT_TEMP_RE = re.compile(
    r"\bmktemp\b(?:\s+(?:-[A-Za-z-]+|\d?>+[^\s);|&]+))*\s*(?=[);|&]|$)"
    r"|\btempfile\.(?:mkstemp|mkdtemp|gettempdir|NamedTemporaryFile|TemporaryDirectory)\b"
    r"|--basetemp\b"
    r"|(?<![A-Za-z_])(?:TMP|TEMP)="
)

# Reasoned exceptions, keyed by path relative to plugins/ plus the literal text.
TMP_ALLOWLIST: dict[str, list[tuple[str, str]]] = {
    "odoo-ai-agents/scripts/setup-steps/40-instance-profile.sh": [
        ("/tmp/profile.json",
         "user-facing copy telling a HUMAN where to hand-write a profile spec before invoking "
         "the step; no script ever writes this path, so it creates no artifact to reclaim"),
    ],
    "odoo-ai-agents/scripts/lib/state_root_permissions.py": [
        ('_SYSTEM_TEMP_DIRS = ("/tmp", "/var/tmp"',
         "the list of system temp directories a state root must not live under; it is only "
         "compared against and nothing is ever created or written there"),
    ],
}


def _normalize(line: str) -> str:
    return re.sub(r"\s+", " ", line)


def _code_files():
    for path in sorted(PLUGINS_DIR.rglob("*")):
        if path.suffix not in _CODE_SUFFIXES or not path.is_file():
            continue
        if any(part in _SKIP_DIR_PARTS for part in path.parts):
            continue
        yield str(path.relative_to(PLUGINS_DIR)), path.read_text(encoding="utf-8", errors="replace")


def tmpdir_hits(text: str, relpath: str = "<text>") -> list[str]:
    return [f"{relpath}:{n}: {_normalize(line).strip()}"
            for n, line in enumerate(text.splitlines(), 1) if TMPDIR_RE.search(_normalize(line))]


def unsanctioned_tmp_hits(text: str, relpath: str = "<text>") -> list[str]:
    allowed = [lit for lit, _ in TMP_ALLOWLIST.get(relpath, [])]
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        line = _normalize(line)
        for m in TMP_PATH_RE.finditer(line):
            at = m.start() - len(STATE_ROOT_FALLBACK_PREFIX)
            if at >= 0 and line[at:m.start()] == STATE_ROOT_FALLBACK_PREFIX:
                continue
            if any(lit in line and line.find(lit) <= m.start() < line.find(lit) + len(lit)
                   for lit in allowed):
                continue
            hits.append(f"{relpath}:{n}: {line.strip()}")
    return hits


def ambient_temp_hits(text: str, relpath: str = "<text>") -> list[str]:
    return [f"{relpath}:{n}: {_normalize(line).strip()}"
            for n, line in enumerate(text.splitlines(), 1) if AMBIENT_TEMP_RE.search(_normalize(line))]


def test_plugin_code_is_discovered():
    assert len(list(_code_files())) >= 100, "the scan walks almost nothing - the roots moved"


@pytest.mark.parametrize("scan, label", [
    (tmpdir_hits, "TMPDIR"),
    (unsanctioned_tmp_hits, "unsanctioned /tmp or /var/tmp"),
    (ambient_temp_hits, "unnamed ambient temp dir (bare mktemp, tempfile.*, --basetemp, TMP=/TEMP=)"),
], ids=["tmpdir", "tmp-path", "ambient-temp"])
def test_plugin_code_names_no_ambient_temp_destination(scan, label):
    hits = [h for relpath, text in _code_files() for h in scan(text, relpath)]
    assert not hits, (
        f"{label} in plugin code - write under the state root (odoo_ai_state_root / "
        "odoo_ai_scratch_dir in scripts/lib/state_reclaim.sh) instead:\n  " + "\n  ".join(hits))


# The detectors must see every spelling and spare compliant text, or the scans above go green
# while the defect walks past.
@pytest.mark.parametrize("scan, line", [
    (tmpdir_hits, 'conf="$(mktemp "${TMPDIR:-/tmp}/odoo-spinup-XXXXXX")"'),
    (tmpdir_hits, 'base = os.environ["TMPDIR"]'),
    (unsanctioned_tmp_hits, 'mkdir -p /tmp/odoo-ai-scratch'),
    (unsanctioned_tmp_hits, 'target = Path("/tmp") / slug'),
    (unsanctioned_tmp_hits, 'mkdir -p /var/tmp/odoo-ai-scratch'),
    (ambient_temp_hits, 'tmp="$(mktemp -d)"'),
    (ambient_temp_hits, 'tmp="$(mktemp -d 2>/dev/null)"'),
    (ambient_temp_hits, 'd = tempfile.mkdtemp()'),
    (ambient_temp_hits, 'pytest tests/ --basetemp=somewhere'),
    (ambient_temp_hits, 'TMP=/somewhere npm install'),
])
def test_detector_catches_the_shape(scan, line):
    assert scan(line, "probe.sh")


@pytest.mark.parametrize("scan, line", [
    (tmpdir_hits, 'tmpdir="$(mktemp -d)"; cur="$tmpdir/cur"'),
    (unsanctioned_tmp_hits, 'printf \'%s\\n\' "${ODOO_AI_HOME:-${HOME:-/tmp}/.odoo-ai}"'),
    (unsanctioned_tmp_hits, 'mount -t tmpfs none /tmpfs-mount'),
    (ambient_temp_hits, 'tmp="$(mktemp -d -p "$scratch")"'),
    (ambient_temp_hits, '_tmp=$(mktemp "${_md}.ethos.XXXXXX")'),
    (ambient_temp_hits, 'an attempt to resolve the state root'),
])
def test_detector_spares_compliant_code(scan, line):
    assert not scan(line, "probe.sh")


def test_allowlist_is_scoped_to_its_file_and_still_needed():
    owner = "odoo-ai-agents/scripts/setup-steps/40-instance-profile.sh"
    line = 'echo "       ODOO_AI_PROFILE_SPEC=/tmp/profile.json bash $0 apply" >&2'
    assert not unsanctioned_tmp_hits(line, owner)
    assert unsanctioned_tmp_hits(line, "odoo-ai-agents/scripts/other.sh")
    for relpath, entries in TMP_ALLOWLIST.items():
        path = PLUGINS_DIR / relpath
        assert path.is_file(), f"stale allowlist entry: {relpath} no longer exists"
        text = _normalize(path.read_text(encoding="utf-8"))
        for literal, _ in entries:
            assert literal in text, f"allowlist exempts {literal!r} in {relpath} but it is gone"
