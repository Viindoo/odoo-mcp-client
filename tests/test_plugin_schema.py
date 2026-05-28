"""Structural validation for .claude-plugin/plugin.json.

Stdlib-only (no third-party deps) so it runs anywhere `python3 -m pytest` works.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / ".claude-plugin" / "plugin.json"


@pytest.fixture(scope="module")
def manifest():
    assert MANIFEST.is_file(), f"missing manifest: {MANIFEST}"
    with MANIFEST.open(encoding="utf-8") as fh:
        return json.load(fh)  # raises if invalid JSON


def test_required_fields(manifest):
    for field in ("name", "description", "license", "homepage"):
        assert field in manifest, f"plugin.json missing '{field}'"
        assert str(manifest[field]).strip(), f"plugin.json '{field}' is empty"


def test_license_is_mit(manifest):
    assert manifest["license"] == "MIT"


def test_homepage_is_url(manifest):
    assert manifest["homepage"].startswith("https://")


def test_skills_dir_present(manifest):
    assert manifest["skills"] == "./skills/"
    skills_dir = ROOT / "skills"
    assert skills_dir.is_dir(), "skills/ directory missing"
    assert any(skills_dir.glob("*/SKILL.md")), "no SKILL.md files found"


def test_agent_files_exist(manifest):
    for rel in manifest.get("agents", []):
        assert (ROOT / rel).is_file(), f"agent file missing: {rel}"


def test_command_files_exist(manifest):
    for rel in manifest.get("commands", []):
        assert (ROOT / rel).is_file(), f"command file missing: {rel}"


def test_mcp_template_present(manifest):
    assert manifest["mcpServers"] == "./.mcp.json"
    mcp = ROOT / ".mcp.json"
    assert mcp.is_file(), ".mcp.json missing"
    with mcp.open(encoding="utf-8") as fh:
        data = json.load(fh)
    assert "odoo-semantic" in data.get("mcpServers", {})


def test_agent_dir_matches_manifest(manifest):
    """Every agents/*.md must be declared in plugin.json.agents."""
    declared = {Path(p).name for p in manifest.get("agents", [])}
    actual = {p.name for p in (ROOT / "agents").glob("*.md")}
    missing = actual - declared
    assert not missing, f"Agent files not declared in plugin.json.agents: {sorted(missing)}"


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
