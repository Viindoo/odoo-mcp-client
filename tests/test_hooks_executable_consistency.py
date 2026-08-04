"""Consistency guard (Phase 3 runtime review, item P13): every hook script `hooks.json` wires via
`bash "${CLAUDE_PLUGIN_ROOT}/hooks/<name>.sh"` should carry the same executable bit as its
siblings.

NOT a runtime-break guard (arbitration A-P3-02.., see the round's consolidated register A-P3-03):
every `hooks.json` entry invokes the script through an explicit `bash <path>` command, so the
interpreter is named directly and the file's own mode bit is never consulted at dispatch time -
`ensure-ethos-import.sh` being 100644 while its 12 siblings were 100755 could not break a session.
This test exists so the mode drift does not silently recur, not because the drift was ever a
functional failure.

Confirmed pre-fix state: `ensure-ethos-import.sh` was mode 100644 (not executable) while its 12
`hooks.json` siblings were all 100755 - fixed via `chmod +x` (a file-mode change, not a git
mutation).
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = ROOT / "plugins" / "odoo-ai-agents" / "hooks"
HOOKS_JSON = HOOKS_DIR / "hooks.json"

_BASH_HOOK_RE = re.compile(r"bash\s+\\?\"\$\{CLAUDE_PLUGIN_ROOT\}/hooks/([^\"\\]+\.sh)\\?\"")


def _hook_script_names() -> list[str]:
    text = HOOKS_JSON.read_text(encoding="utf-8")
    # Parse as JSON first to confirm the file is well-formed (not just regex-scraped), then
    # extract every `bash ".../hooks/<name>.sh"` command string via regex - the JSON schema
    # nests commands under an arbitrary number of event/matcher levels, and the regex is the
    # stable contract (every hook is dispatched this exact way) rather than a schema-shaped walk.
    json.loads(text)
    return sorted(set(_BASH_HOOK_RE.findall(text)))


def test_every_hook_script_is_executable():
    names = _hook_script_names()
    assert names, f"no hook scripts parsed out of {HOOKS_JSON} - regex or file drifted"

    non_executable = []
    for name in names:
        path = HOOKS_DIR / name
        assert path.is_file(), f"hooks.json references missing script: {path}"
        mode = path.stat().st_mode
        if not (mode & stat.S_IXUSR):
            non_executable.append(f"{path} (mode {oct(stat.S_IMODE(mode))})")

    assert not non_executable, (
        "hooks.json-referenced script(s) missing the owner-executable bit its siblings all "
        "carry (consistency only - hooks.json always invokes `bash <path>`, so this is never a "
        "dispatch failure):\n" + "\n".join(non_executable)
    )


def test_hook_scripts_share_one_consistent_mode():
    names = _hook_script_names()
    modes = {name: stat.S_IMODE(os.stat(HOOKS_DIR / name).st_mode) for name in names}
    distinct = set(modes.values())
    assert len(distinct) == 1, (
        "hooks.json-referenced scripts do not all share the same file mode "
        f"(found {sorted(oct(m) for m in distinct)}) - drift like this is the P13 defect class:\n"
        + "\n".join(f"{name}: {oct(mode)}" for name, mode in sorted(modes.items()))
    )
