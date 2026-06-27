"""Structural validation for the two split plugin manifests.

After the v2 split, the single `odoo-semantic` plugin became two:
  - plugins/odoo-ai-agents/  (skills + agents + workflow commands)
  - plugins/odoo-semantic-mcp/     (MCP server connection + connect command)

Each manifest is validated against its own plugin root, and relative paths
(``./agents/...``, ``./commands/...``, ``./.mcp.json``) resolve from the
directory that contains the manifest.

Stdlib-only (no third-party deps) so it runs anywhere `python3 -m pytest` works.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGINS_DIR = ROOT / "plugins"
SKILLS_PLUGIN = PLUGINS_DIR / "odoo-ai-agents"
MCP_PLUGIN = PLUGINS_DIR / "odoo-semantic-mcp"
GIT_PLUGIN = PLUGINS_DIR / "git-toolkit"

SKILLS_MANIFEST = SKILLS_PLUGIN / ".claude-plugin" / "plugin.json"
MCP_MANIFEST = MCP_PLUGIN / ".claude-plugin" / "plugin.json"
GIT_MANIFEST = GIT_PLUGIN / ".claude-plugin" / "plugin.json"

# (plugin_root, manifest_path) pairs for the manifests that share common fields.
ALL_MANIFESTS = [
    pytest.param(SKILLS_PLUGIN, SKILLS_MANIFEST, id="odoo-ai-agents"),
    pytest.param(MCP_PLUGIN, MCP_MANIFEST, id="odoo-semantic-mcp"),
    pytest.param(GIT_PLUGIN, GIT_MANIFEST, id="git-toolkit"),
]

# Each plugin declares its own license; assert the EXACT expected value per plugin
# (git-toolkit is intentionally Apache-2.0 for its explicit patent grant; the two
# odoo plugins stay MIT). A new plugin with no entry here fails loudly.
EXPECTED_LICENSE = {
    "odoo-ai-agents": "MIT",
    "odoo-semantic-mcp": "MIT",
    "git-toolkit": "Apache-2.0",
}


def _load(manifest_path):
    assert manifest_path.is_file(), f"missing manifest: {manifest_path}"
    with manifest_path.open(encoding="utf-8") as fh:
        return json.load(fh)  # raises if invalid JSON


@pytest.fixture(scope="module")
def skills_manifest():
    return _load(SKILLS_MANIFEST)


@pytest.fixture(scope="module")
def mcp_manifest():
    return _load(MCP_MANIFEST)


# ---------------------------------------------------------------------------
# Common manifest checks (apply to BOTH plugins)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("plugin_root, manifest_path", ALL_MANIFESTS)
def test_required_fields(plugin_root, manifest_path):
    manifest = _load(manifest_path)
    for field in ("name", "description", "license", "homepage"):
        assert field in manifest, f"{manifest_path.name} missing '{field}'"
        assert str(manifest[field]).strip(), f"{manifest_path.name} '{field}' is empty"


@pytest.mark.parametrize("plugin_root, manifest_path", ALL_MANIFESTS)
def test_license_is_expected(plugin_root, manifest_path):
    expected = EXPECTED_LICENSE.get(plugin_root.name)
    assert expected is not None, f"declare an expected license for plugin {plugin_root.name!r}"
    assert _load(manifest_path)["license"] == expected, (
        f"{plugin_root.name} license must be {expected!r}"
    )


@pytest.mark.parametrize("plugin_root, manifest_path", ALL_MANIFESTS)
def test_homepage_is_url(plugin_root, manifest_path):
    assert _load(manifest_path)["homepage"].startswith("https://")


@pytest.mark.parametrize("plugin_root, manifest_path", ALL_MANIFESTS)
def test_command_files_exist(plugin_root, manifest_path):
    """Every command rel path resolves to a file under its own plugin root."""
    manifest = _load(manifest_path)
    for rel in manifest.get("commands", []):
        assert (plugin_root / rel).is_file(), (
            f"{manifest_path.name}: command file missing: {rel}"
        )


# ---------------------------------------------------------------------------
# Skills plugin (odoo-ai-agents)
# ---------------------------------------------------------------------------


def test_skills_manifest_name(skills_manifest):
    assert skills_manifest["name"] == "odoo-ai-agents"


def test_skills_dir_present(skills_manifest):
    assert skills_manifest["skills"] == "./skills/"
    skills_dir = SKILLS_PLUGIN / "skills"
    assert skills_dir.is_dir(), "plugins/odoo-ai-agents/skills/ directory missing"
    assert any(skills_dir.glob("*/SKILL.md")), "no SKILL.md files found"


def test_skills_agent_files_exist(skills_manifest):
    for rel in skills_manifest.get("agents", []):
        assert (SKILLS_PLUGIN / rel).is_file(), f"agent file missing: {rel}"


def test_skills_agent_dir_matches_manifest(skills_manifest):
    """Every agents/*.md must be declared in plugin.json.agents."""
    declared = {Path(p).name for p in skills_manifest.get("agents", [])}
    actual = {p.name for p in (SKILLS_PLUGIN / "agents").glob("*.md")}
    missing = actual - declared
    assert not missing, f"Agent files not declared in plugin.json.agents: {sorted(missing)}"


def test_skills_depends_on_mcp(skills_manifest):
    """Intent: the skills plugin must declare a dependency on the MCP plugin so
    installing skills auto-pulls the server connection."""
    deps = skills_manifest.get("dependencies", [])
    assert "odoo-semantic-mcp" in deps, (
        f"odoo-ai-agents must depend on 'odoo-semantic-mcp'; "
        f"found dependencies={deps}"
    )
    assert "git-toolkit" in deps, (
        f"odoo-ai-agents must depend on 'git-toolkit'; "
        f"found dependencies={deps}"
    )


# ---------------------------------------------------------------------------
# MCP plugin (odoo-semantic-mcp)
# ---------------------------------------------------------------------------


def test_mcp_manifest_name(mcp_manifest):
    assert mcp_manifest["name"] == "odoo-semantic-mcp"


def test_mcp_template_present(mcp_manifest):
    assert mcp_manifest["mcpServers"] == "./.mcp.json"
    mcp = MCP_PLUGIN / ".mcp.json"
    assert mcp.is_file(), "plugins/odoo-semantic-mcp/.mcp.json missing"
    with mcp.open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "odoo-semantic" in data.get("mcpServers", {})


def test_mcp_user_config(mcp_manifest):
    """userConfig must expose a required, sensitive api_key and a defaulted mcp_url."""
    user_config = mcp_manifest.get("userConfig", {})
    assert "api_key" in user_config, "userConfig missing 'api_key'"
    api_key = user_config["api_key"]
    assert api_key.get("required") is True, "api_key must be required"
    assert api_key.get("sensitive") is True, "api_key must be marked sensitive"

    assert "mcp_url" in user_config, "userConfig missing 'mcp_url'"
    assert user_config["mcp_url"].get("default"), "mcp_url must declare a default"


def test_mcp_connect_command_exists(mcp_manifest):
    commands = mcp_manifest.get("commands", [])
    assert "./commands/connect.md" in commands, (
        f"mcp manifest must declare './commands/connect.md'; found {commands}"
    )
    assert (MCP_PLUGIN / "commands" / "connect.md").is_file(), "connect.md missing"


# ---------------------------------------------------------------------------
# Cross-cutting hygiene
# ---------------------------------------------------------------------------


def test_no_server_internals_leaked():
    """The MIT client must not embed server-only admin commands or venv paths."""
    banned = (".venv/odoo-semantic-mcp", "src.manager create-api-key")
    offenders = []
    for path in ROOT.rglob("*"):
        if path.is_dir() or ".git" in path.parts or "node_modules" in path.parts:
            continue
        if path.suffix not in {".md", ".json", ".yml", ".yaml", ".sh", ""}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for token in banned:
            if token in text:
                offenders.append(f"{path.relative_to(ROOT)} -> {token}")
    assert not offenders, "server internals leaked into client repo:\n" + "\n".join(offenders)
