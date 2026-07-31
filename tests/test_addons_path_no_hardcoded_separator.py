"""Structural guard: nobody may hand-roll an addons_path separator outside the
two SSOT homes (scripts/lib/instances_io.py's join_addons_path/split_addons_path,
and scripts/lib/resolve_instances.sh's _addons_path_to_array).

This class of bug has recurred repeatedly, each time as a NEW hardcoded literal
at a DIFFERENT site, after a previous fix only touched one join/split site:
  - a hardcoded `${arg_addons//:/, }` normalize block appeared in
    55-instance-ops.sh.
  - allocator.py's producer-side join was flipped to comma while
    55-instance-ops.sh's own hardcoded `IFS=':'` consumer was left stranded on
    colon, with no signal.
  - a hardcoded `IFS=','` appeared in 50-instance-spinup.sh that disagreed
    with instances_io.py's colon-joined INST_ADDONS_PATH at the time.

None of those would have shipped if a lint like this one already existed:
every NEW hardcoded separator for an addons_path-shaped variable, anywhere
under scripts/ except the two SSOT files, is a hard failure naming file:line.

Scope is deliberately narrow (scripts/*.py and scripts/*.sh only) - prose sites
(agents/*.md, skills/*.md, snippets/*.md) are corrected by hand, not scanned
here (a doc claim cannot desync a runtime split/join).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = ROOT / "plugins" / "odoo-ai-agents" / "scripts"

# The two SSOT homes. Hardcoding the separator INSIDE these two files is
# expected - they ARE the SSOT that every other producer/consumer must call
# instead. This allowlist is SHRINK-ONLY: removing an entry (because a file
# stopped being a separator home) is fine; adding one requires the new file to
# genuinely become the join/split SSOT, not just a convenient exception.
ALLOWLIST = {
    (SCRIPTS_DIR / "lib" / "instances_io.py").resolve(),
    (SCRIPTS_DIR / "lib" / "resolve_instances.sh").resolve(),
}

# `IFS=':'`/`IFS=","` (quoted or bare) immediately followed by `read -ra` on
# the SAME line, where the line also mentions "addons" or "path" - covers the
# `IFS=':' read -ra _paths <<< "$addons_path"` shape every consumer used
# before being migrated onto `_addons_path_to_array`.
_IFS_READ_RE = re.compile(r"""IFS=['"]?[,:]['"]?\s+read\s+-ra""")

# `",".join(...)` / `":".join(...)` (Python) - a hardcoded single-character
# comma/colon join. Matched only on lines that also mention "addon" so a
# generic, non-addons join (e.g. allocator.py's own space-joined ALLOC_PORTS
# helper) is not flagged.
_JOIN_LITERAL_RE = re.compile(r"""["'][,:]["']\.join\(""")

# Bash substitution operators that hand-convert one separator into the other
# (the `${arg_addons//:/, }` normalize idiom).
_BASH_SUBST_RE = re.compile(r"//[,:]/")


def _iter_scanned_files():
    for pattern in ("*.py", "*.sh"):
        for path in sorted(SCRIPTS_DIR.rglob(pattern)):
            if path.resolve() in ALLOWLIST:
                continue
            yield path


# How many lines ABOVE a hit to also scan for the word "addon" - catches an
# abbreviated local (e.g. `ap = it.get("addons_path", [])` a couple of lines
# above `ap = ",".join(...)`) instead of requiring the mention on the exact
# same line. Deliberately "addon" only (not the much more common "path", which
# would false-positive on unrelated venv_path/toml_path/log_path locals).
_CONTEXT_LINES = 3


def _scan(pattern: re.Pattern, *, require_addons_mention: bool) -> list[str]:
    hits = []
    for path in _iter_scanned_files():
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            if not pattern.search(line):
                continue
            if require_addons_mention:
                window = "\n".join(lines[max(0, i - _CONTEXT_LINES):i + 1])
                if "addon" not in window.lower():
                    continue
            hits.append(f"{path.relative_to(ROOT)}:{i + 1}: {line.strip()}")
    return hits


def test_no_hardcoded_ifs_comma_or_colon_split_outside_ssot():
    hits = _scan(_IFS_READ_RE, require_addons_mention=True)
    assert not hits, (
        "Hardcoded IFS=','/IFS=':' + read -ra found outside the addons_path "
        "SSOT (scripts/lib/instances_io.py / scripts/lib/resolve_instances.sh). "
        "Use `_addons_path_to_array <arrname> \"$value\"` instead:\n"
        + "\n".join(hits)
    )


def test_no_hardcoded_comma_or_colon_join_for_addons_outside_ssot():
    hits = _scan(_JOIN_LITERAL_RE, require_addons_mention=True)
    assert not hits, (
        "Hardcoded ','.join(...) / ':'.join(...) found for an addons-related "
        "value outside the SSOT. Use instances_io.join_addons_path(...) "
        "instead:\n" + "\n".join(hits)
    )


def test_no_hardcoded_bash_colon_comma_substitution_for_addons_outside_ssot():
    hits = []
    for path in _iter_scanned_files():
        if path.suffix != ".sh":
            continue
        text = path.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if _BASH_SUBST_RE.search(line) and (
                "addon" in line.lower() or "arg_addons" in line.lower()
            ):
                hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    assert not hits, (
        "Hardcoded bash separator-substitution (//:/  or  //,/ ) found for an "
        "addons-related variable outside the SSOT. Use "
        "_addons_path_to_array instead:\n" + "\n".join(hits)
    )
