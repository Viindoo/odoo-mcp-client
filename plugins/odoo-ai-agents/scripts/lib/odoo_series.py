"""odoo_series.py - derive the Odoo major series (e.g. "17.0") from a checkout on disk.

The naive heuristic this module exists to displace - "find the first
__manifest__.py, read `version`, take the first two dotted components" - is
wrong on every one of the 12 indexed OSM series (8.0-19.0): it finds NOTHING
on 8.0/9.0 (whose descriptor
is `__openerp__.py`, not `__manifest__.py`), and even where it finds a file the
`version` key's first two components are typically the ADDON's own version
(stock core `base` declares `1.3`/`1.4`, not the series) - never the series.
Full evidence trail: the OSM-grounded design note this module implements,
Section E ("Version correctness of the promoted checkout-derivation rung").

Ordered derivation, STOP at the first step that yields anything - later steps
are strictly weaker evidence and must never override an earlier one. Only
steps 1 and 2 read a fact that IS the series by definition, so only they
resolve one; steps 3-5 surface weaker evidence with NEEDS_CONTEXT:

  1. Core `release.py` (authoritative, covers 8.0-19.0). The core package dir
     is `openerp/` on v8-v9 and `odoo/` on v10+, so both are probed, at a
     depth that survives a nested checkout layout (maxdepth 5, mirroring the
     shell `find -maxdepth 5` this derivation is normatively specified with).
     Series = `major_version` when the file assigns it as a plain string
     literal (this is the attribute Odoo core itself calls, e.g.
     `return release.major_version`), else the first two elements of
     `version_info` joined with a dot (e.g. `(17, 0, 0, FINAL, 0, '')` ->
     `17.0`). A SaaS build may spell the first element as a string
     (`'saas~17.2'`): the numeric major is extracted and the minor is forced
     to `0`. The parsed major is cross-checked against the package dir it was
     read from (`openerp/` implies 8 or 9, `odoo/` implies >= 10); a
     candidate that contradicts its own package dir is distrusted and
     skipped, never returned.
  2. A series-named git branch (for an addons-only repo with no core
     package). Accepts ONLY a name matching `^[0-9]{1,2}\\.0$`, optionally
     after a remote prefix (e.g. `origin/17.0`). A feature-branch name is not
     evidence - falls through.
  3. The manifest `version` key - a CANDIDATE, never a result. A value earns
     candidacy only when it is series-PREFIXED: at least four dot-separated
     numeric segments, the second exactly `0`, and a leading major at or above
     `_MIN_SERIES_MAJOR`. `17.0.1.0.0` and `10.0.1.0` qualify; `1.0`, `1.3`,
     `1.0.9`, `1.0.0`, `0.5.5` and `2.0.1` do not - those are the ADDON's own
     version, the shape stock Odoo core and the Viindoo distributions ship at
     every series. The second segment alone discriminates nothing (short forms
     hit `0` constantly), so the segment count and the floor are what separate
     a series from an addon's version. A decorated value (`v17.0.1.0.0`,
     `17.0.1.0.0-rc1`) does not qualify - the pattern is anchored at both
     ends. EVERY manifest under the root is read (both descriptor filenames,
     no cap) and every candidate must agree on one series; disagreement is
     inconclusive, never resolved by majority vote - and agreement is not a
     correctness check either, since one rule applied uniformly to the wrong
     field agrees with itself. Even unanimous candidates are not the series: a
     code-level upgrade leaves the manifest `version` unbumped, so a
     series-prefixed value can name an earlier series than the checkout, and
     those two cases are byte-identical on disk. So step 3 NEVER emits
     `SERIES_STATUS=OK` and NEVER populates `SERIES` - it reports the
     candidate as an explicitly weak `SERIES_HINT` with NEEDS_CONTEXT and
     exit 3, for the caller to confirm against its own words or ask about.
  4. Era only (cannot pin one series - reports a range and NEEDS_CONTEXT,
     never guesses). Only `__openerp__.py` present anywhere -> era "8.0-9.0".
     Any `__manifest__.py` present -> era "10.0+" (Odoo loads
     `__manifest__.py` and silently ignores a co-located `__openerp__.py`,
     so its presence alone proves nothing beyond "not v8/v9").
  5. Last-resort hints (`setup.py`, `debian/changelog`) - existence only,
     never parsed for a series value, always surfaced as a HINT rather than a
     result: OSM is silent on both files' content at every series, so neither
     is trustworthy evidence.

If every step fails, the result is NEEDS_CONTEXT with no series at all.
NEVER default to a series - a wrong series silently produces wrong API
choices downstream. Edition (Community vs Enterprise) is deliberately NOT
covered here: it is not determinable from disk on any series (see the design
note's Section E.3) and must not be inferred by this module.

stdlib only (re, os, ast, subprocess, pathlib) - no third-party deps, matching
every other helper in this directory.

CLI:
    python3 odoo_series.py detect <root>
        Prints shell-eval-able KEY=VALUE lines (shlex.quote'd), mirroring
        instances_io.py's INST_* / allocator.py's ALLOC_* convention:

            SERIES_STATUS=OK|NEEDS_CONTEXT
            SERIES=<value>            # e.g. "17.0"; empty when unresolved,
                                      # and only step 1 or 2 ever fills it
            SERIES_STEP=<1|2|3|4|5>   # which ordered step produced the
                                      # result; empty when nothing resolved
            SERIES_ERA=<value>        # step 4 only, e.g. "8.0-9.0"/"10.0+";
                                      # empty otherwise
            SERIES_EVIDENCE=<text>    # citation for steps 1-3: an absolute
                                      # path or the git branch name; empty
                                      # for steps 4-5
            SERIES_HINT=<text>        # steps 3 and 5 - explicitly WEAK, never
                                      # a resolved series: step 3's
                                      # unconfirmed manifest candidate plus
                                      # why it is weak, step 5's ';'-joined
                                      # last-resort file paths; empty
                                      # otherwise

        Exit codes:
            0   SERIES_STATUS=OK (a series was resolved via step 1 or step 2)
            3   SERIES_STATUS=NEEDS_CONTEXT (a manifest candidate, an era, a
                hint, or nothing at all was found - distinguishes "ask the
                user" from success)
            2   usage error (bad/missing CLI arguments)
            1   <root> does not exist or is not a directory
"""

from __future__ import annotations

import ast
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

__all__ = ["detect"]

_MANIFEST_NAMES = ("__manifest__.py", "__openerp__.py")
_CORE_PKG_NAMES = ("odoo", "openerp")
_MAXDEPTH = 5  # mirrors the normative `find "$ROOT" -maxdepth 5 ...` derivation

# The era floor for a series-prefixed manifest `version`, declared ONCE here. The oldest series the
# era boundaries cover is 8.0 (snippets/odoo-era-boundaries.md rows 5-6), so a leading major below
# this is an addon's own version number and never a series - which is what kills the whole real
# short-form population, whose majors are 0 and 1. Deliberately a FLOOR WITH NO CEILING: a series
# above every one named anywhere in this repo must still classify, so no edit is due when the next
# major ships. A closed range would silently start rejecting the newest series instead.
_MIN_SERIES_MAJOR = 8

_MAJOR_VERSION_RE = re.compile(r"""major_version\s*=\s*['"]([^'"]+)['"]""")
_VERSION_INFO_RE = re.compile(r"version_info\s*=\s*\(([^)]*)\)")
_BRANCH_SERIES_RE = re.compile(r"^(?:[\w.\-]+/)?([0-9]{1,2}\.0)$")
# A series-PREFIXED manifest `version`: `<major>.0.<x>.<y>[...]` - four or more dot-separated
# numeric segments with the second exactly `0`. Anchored at BOTH ends, so a decorated value
# (`v17.0.1.0.0`, `17.0.1.0.0-rc1`) is not this shape.
_SERIES_PREFIXED_VERSION_RE = re.compile(r"^([0-9]+)\.0(?:\.[0-9]+){2,}$")
_MANIFEST_VERSION_KEY_RE = re.compile(r"""['"]version['"]\s*:\s*['"]([^'"]+)['"]""")

# Why a step-3 candidate can never be the answer, carried in the output so a caller reading only
# the KEY=VALUE lines sees the reason and not just a number.
_MANIFEST_CANDIDATE_HINT = (
    "manifest candidate {series} - UNCONFIRMED, never a resolved series: a code-level upgrade "
    "leaves the manifest version unbumped, so a series prefix can name an earlier series than "
    "this checkout. Confirm it against the caller's own words, or ask."
)


# --------------------------------------------------------------------------- #
# shared filesystem walk (mirrors `find "$ROOT" -maxdepth N`)
# --------------------------------------------------------------------------- #
def _find_maxdepth(root: Path, maxdepth: int):
    """Yield every file under `root`, at find(1) depth <= maxdepth (root itself
    is depth 0; each path component below it is +1). Prunes descent past the
    limit instead of walking the whole tree and filtering after the fact."""
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_depth = len(Path(dirpath).parts) - base_depth
        if rel_depth >= maxdepth:
            dirnames[:] = []
        if rel_depth < maxdepth:
            for fn in filenames:
                yield Path(dirpath) / fn


# --------------------------------------------------------------------------- #
# step 1 - core release.py
# --------------------------------------------------------------------------- #
def _parse_release_py_text(text: str) -> str | None:
    m = _MAJOR_VERSION_RE.search(text)
    if m:
        raw = m.group(1).strip()
        dm = re.match(r"^(\d{1,2})\.", raw)
        if dm:
            return f"{int(dm.group(1))}.0"
    m2 = _VERSION_INFO_RE.search(text)
    if m2:
        parts = [p.strip() for p in m2.group(1).split(",") if p.strip()]
        if len(parts) >= 2:
            first = parts[0]
            if first[:1] in ("'", '"'):
                inner = first[1:-1] if len(first) >= 2 else ""
                dm3 = re.search(r"(\d{1,2})", inner)
                return f"{int(dm3.group(1))}.0" if dm3 else None
            try:
                major = int(first)
            except ValueError:
                return None
            try:
                minor = int(parts[1])
            except ValueError:
                minor = 0
            return f"{major}.{minor}"
    return None


def _step1_release_py(root: Path):
    candidates = [
        p
        for p in _find_maxdepth(root, _MAXDEPTH)
        if p.name == "release.py" and p.parent.name in _CORE_PKG_NAMES
    ]

    def _sort_key(p: Path):
        depth = len(p.relative_to(root).parts)
        pkg_rank = 0 if p.parent.name == "odoo" else 1  # prefer odoo/ at equal depth
        return (depth, pkg_rank)

    for path in sorted(candidates, key=_sort_key):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        series = _parse_release_py_text(text)
        if series is None:
            continue
        major = int(series.split(".", 1)[0])
        pkg = path.parent.name
        # Cross-check the parsed number against the package dir it came from -
        # a contradiction (e.g. `odoo/release.py` claiming major 9) means the
        # literal is not trustworthy, so this candidate is skipped rather than
        # returned. openerp/ -> only 8 or 9 is consistent; odoo/ -> only >= 10.
        if pkg == "openerp" and major not in (8, 9):
            continue
        if pkg == "odoo" and major < 10:
            continue
        return series, str(path)
    return None, None


# --------------------------------------------------------------------------- #
# step 2 - series-named git branch
# --------------------------------------------------------------------------- #
def _step2_git_branch(root: Path):
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None, None
    if proc.returncode != 0:
        return None, None
    branch = proc.stdout.strip()
    m = _BRANCH_SERIES_RE.match(branch)
    if not m:
        return None, None
    return m.group(1), branch


# --------------------------------------------------------------------------- #
# step 3 - manifest version, a weak CANDIDATE only (never a resolved series)
# --------------------------------------------------------------------------- #
def _series_from_manifest_version(version: str) -> str | None:
    """Return the series a series-PREFIXED manifest `version` names, or None when the value is not
    that shape at all. Three necessary conditions: >= 4 numeric segments, second segment exactly
    `0`, leading major at or above `_MIN_SERIES_MAJOR`. The second segment on its own separates
    nothing - real short forms hit `0` constantly (`1.0`, `1.0.0`, `1.0.9`) - so the segment count
    and the floor carry the discrimination."""
    m = _SERIES_PREFIXED_VERSION_RE.match(version)
    if not m:
        return None
    major = int(m.group(1))
    if major < _MIN_SERIES_MAJOR:
        return None
    return f"{major}.0"


def _extract_manifest_version(text: str) -> str | None:
    try:
        data = ast.literal_eval(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        data = None
    if isinstance(data, dict):
        v = data.get("version")
        if isinstance(v, str):
            return v
    m = _MANIFEST_VERSION_KEY_RE.search(text)
    return m.group(1) if m else None


def _step3_manifest_candidate(root: Path):
    """Return (candidate_series, citation_path) when EVERY series-prefixed manifest under `root`
    agrees on one series, else (None, None). The candidate is weak evidence by construction - the
    caller must not present it as a resolved series.

    Every manifest in range is read, with no cap: a cap applied to the walk order hides the one
    series-prefixed manifest behind its short-form siblings and makes the answer depend on
    `os.walk` ordering. The walk is already bounded by `_MAXDEPTH`. Candidates are sorted so the
    cited path is deterministic rather than whichever the walk reached first."""
    found: dict[str, list[Path]] = {}
    for path in sorted(p for p in _find_maxdepth(root, _MAXDEPTH) if p.name in _MANIFEST_NAMES):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        version = _extract_manifest_version(text)
        if version is None:
            continue
        series = _series_from_manifest_version(version)
        if series is None:
            continue  # an addon's own version (1.0, 1.3, 1.0.9, ...) - not evidence of a series
        found.setdefault(series, []).append(path)
    if len(found) != 1:
        # Zero candidates, or candidates naming different series - neither is evidence. Agreement
        # is not a correctness check: one rule applied uniformly to the wrong field agrees with
        # itself, which is exactly how a systematic misread produces unanimity.
        return None, None
    (series, paths), = found.items()
    return series, str(paths[0])


# --------------------------------------------------------------------------- #
# step 4 - era only
# --------------------------------------------------------------------------- #
def _step4_era(root: Path) -> str | None:
    names = {p.name for p in _find_maxdepth(root, _MAXDEPTH) if p.name in _MANIFEST_NAMES}
    if "__manifest__.py" in names:
        return "10.0+"
    if "__openerp__.py" in names:
        return "8.0-9.0"
    return None


# --------------------------------------------------------------------------- #
# step 5 - last-resort hints (existence only, never parsed into a series)
# --------------------------------------------------------------------------- #
def _step5_hints(root: Path) -> list[str]:
    hints = []
    for p in _find_maxdepth(root, _MAXDEPTH):
        if p.name == "setup.py" or (p.name == "changelog" and p.parent.name == "debian"):
            hints.append(str(p))
    return hints


# --------------------------------------------------------------------------- #
# public API
# --------------------------------------------------------------------------- #
def detect(root: str | Path) -> dict:
    """Run the ordered derivation against `root`. Returns a dict with keys
    status ("OK"|"NEEDS_CONTEXT"), series, step, era, evidence, hint - every
    key always present (empty string when not applicable). Never raises for a
    missing/empty tree; callers checking a path's existence do so themselves
    (the CLI wrapper below returns exit 1 for a non-directory root)."""
    root = Path(root)

    series, evidence = _step1_release_py(root)
    if series:
        return {"status": "OK", "series": series, "step": "1", "era": "", "evidence": evidence, "hint": ""}

    series, evidence = _step2_git_branch(root)
    if series:
        return {"status": "OK", "series": series, "step": "2", "era": "", "evidence": evidence, "hint": ""}

    # Step 3 is on the WEAK side of the OK/NEEDS_CONTEXT line, next to steps 4-5: it reads an
    # addon's own version number, a different kind of fact from `release.py` or a series-named
    # branch, and one this ecosystem's own upgrade convention freezes across series. So it fills
    # `hint`, never `series`, and the exit code stays 3 - a shell caller testing `$? -eq 0` can
    # never mistake a manifest guess for a resolved series.
    candidate, evidence = _step3_manifest_candidate(root)
    if candidate:
        return {
            "status": "NEEDS_CONTEXT",
            "series": "",
            "step": "3",
            "era": "",
            "evidence": evidence,
            "hint": _MANIFEST_CANDIDATE_HINT.format(series=candidate),
        }

    era = _step4_era(root)
    if era:
        return {"status": "NEEDS_CONTEXT", "series": "", "step": "4", "era": era, "evidence": "", "hint": ""}

    hints = _step5_hints(root)
    if hints:
        return {
            "status": "NEEDS_CONTEXT",
            "series": "",
            "step": "5",
            "era": "",
            "evidence": "",
            "hint": ";".join(hints),
        }

    return {"status": "NEEDS_CONTEXT", "series": "", "step": "", "era": "", "evidence": "", "hint": ""}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _emit(name: str, value: str) -> None:
    print(f"{name}={shlex.quote(str(value))}")


def _cmd_detect(argv: list) -> int:
    if len(argv) != 1 or not argv[0]:
        sys.stderr.write("Usage: odoo_series.py detect <root>\n")
        return 2
    root = Path(argv[0])
    if not root.is_dir():
        sys.stderr.write(f"odoo_series.py: {root} is not a directory.\n")
        return 1
    result = detect(root)
    _emit("SERIES_STATUS", result["status"])
    _emit("SERIES", result["series"])
    _emit("SERIES_STEP", result["step"])
    _emit("SERIES_ERA", result["era"])
    _emit("SERIES_EVIDENCE", result["evidence"])
    _emit("SERIES_HINT", result["hint"])
    return 0 if result["status"] == "OK" else 3


def main(argv: list) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "detect":
        return _cmd_detect(argv[1:])
    sys.stderr.write(f"Unknown subcommand: {argv[0]!r}. Use 'detect'.\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
