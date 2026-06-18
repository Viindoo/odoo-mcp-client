"""Guard: the client version stays internally consistent and in lockstep.

`VERSION` (repo-level single source of truth) and the `odoo-ai-agents`
plugin's `plugin.json.version` MUST be equal - bumping one without the other is
exactly how 2.4.0/2.4.1 shipped with no matching CHANGELOG section. CI fails here
if they drift. Use `scripts/bump-version.sh <major|minor|patch>` to bump both
together (and cut the changelog) so this test stays green.

The `odoo-semantic-mcp` plugin versions independently and is intentionally not
checked against VERSION.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
SKILLS_MANIFEST = ROOT / "plugins" / "odoo-ai-agents" / ".claude-plugin" / "plugin.json"
CHANGELOG = ROOT / "CHANGELOG.md"

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _version():
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def _plugin_version():
    return json.loads(SKILLS_MANIFEST.read_text(encoding="utf-8"))["version"]


def test_version_is_semver():
    v = _version()
    assert SEMVER.match(v), f"VERSION must be MAJOR.MINOR.PATCH, got {v!r}"


def test_version_and_plugin_in_lockstep():
    v, pv = _version(), _plugin_version()
    assert v == pv, (
        f"VERSION ({v}) and odoo-ai-agents/plugin.json version ({pv}) have drifted. "
        f"Bump both together with scripts/bump-version.sh."
    )


def test_changelog_has_section_for_current_version():
    """A released VERSION should have a matching CHANGELOG section (or sit under
    [Unreleased] until cut). This catches a bump that forgot to cut the log."""
    v = _version()
    text = CHANGELOG.read_text(encoding="utf-8")
    assert f"## [{v}]" in text or "## [Unreleased]" in text, (
        f"CHANGELOG.md has neither a '## [{v}]' section nor '## [Unreleased]'"
    )
