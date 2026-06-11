"""Validate that every MCP snippet in plugins/odoo-ai-agents/snippets/ is
well-formed and follows the project conventions:

- Parses as valid JSON (no comments allowed in JSON).
- Uses X-API-Key auth header, not Authorization / Bearer.
- References the canonical server URL and server name.
- Contains no machine-specific paths (/home/...).
- Contains no real API keys (only allowed placeholder patterns).
- Uses the correct top-level key for its editor family.

stdlib only -- no PyYAML or third-party imports.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SNIPPETS = ROOT / "plugins" / "odoo-ai-agents" / "snippets"

JSON_FILES = sorted(SNIPPETS.glob("*.json"))


def _stem(path: Path) -> str:
    return path.stem


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_json_parses(snippet):
    """Every snippet must be valid JSON."""
    text = snippet.read_text(encoding="utf-8")
    # This raises json.JSONDecodeError (a ValueError) on invalid JSON
    json.load(snippet.open(encoding="utf-8"))


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_uses_x_api_key_header(snippet):
    """Snippet must reference X-API-Key, not Authorization or Bearer."""
    text = snippet.read_text(encoding="utf-8")
    assert "X-API-Key" in text, f"{snippet.name}: must contain 'X-API-Key'"


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_no_authorization_header(snippet):
    """Snippet must not use Authorization header (wrong auth scheme)."""
    text = snippet.read_text(encoding="utf-8")
    assert "Authorization" not in text, (
        f"{snippet.name}: must not contain 'Authorization' (use X-API-Key instead)"
    )


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_no_bearer_token(snippet):
    """Snippet must not use Bearer token scheme."""
    text = snippet.read_text(encoding="utf-8")
    assert "Bearer" not in text, (
        f"{snippet.name}: must not contain 'Bearer' (use X-API-Key instead)"
    )


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_canonical_url(snippet):
    """Snippet must reference the canonical MCP endpoint."""
    text = snippet.read_text(encoding="utf-8")
    assert "odoo-semantic.viindoo.com/mcp" in text, (
        f"{snippet.name}: must contain 'odoo-semantic.viindoo.com/mcp'"
    )


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_server_name(snippet):
    """Snippet must declare the server as 'odoo-semantic'."""
    text = snippet.read_text(encoding="utf-8")
    assert "odoo-semantic" in text, (
        f"{snippet.name}: must contain server name 'odoo-semantic'"
    )


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_no_home_path(snippet):
    """Snippet must not contain machine-specific /home/ paths."""
    text = snippet.read_text(encoding="utf-8")
    assert "/home/" not in text, (
        f"{snippet.name}: must not contain '/home/' (not portable)"
    )


# Pattern for real OSM API keys: osm_ followed by 4+ alphanumeric chars.
# Allowed placeholder patterns: <YOUR_API_KEY>, ${input:...}, ${env:...}
_REAL_KEY_RE = re.compile(r"osm_[A-Za-z0-9]{4}")


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_no_real_api_key(snippet):
    """Snippet must not contain a real API key (only placeholders allowed)."""
    text = snippet.read_text(encoding="utf-8")
    match = _REAL_KEY_RE.search(text)
    assert match is None, (
        f"{snippet.name}: looks like a real API key was embedded "
        f"(matched '{match.group()}') -- use <YOUR_API_KEY>, ${{input:...}}, "
        f"or ${{env:...}} instead"
    )


# ---------------------------------------------------------------------------
# Per-editor top-level key check
# ---------------------------------------------------------------------------

def _expected_top_key(stem: str) -> str:
    """Return the required JSON top-level key for the given file stem."""
    if stem.startswith("vscode"):
        return "servers"
    if stem.startswith("zed"):
        return "context_servers"
    # cursor, antigravity, windsurf, junie, and any future mcpServers-family
    return "mcpServers"


@pytest.mark.parametrize("snippet", JSON_FILES, ids=_stem)
def test_top_level_key(snippet):
    """Each editor family must use the correct top-level JSON key."""
    data = json.loads(snippet.read_text(encoding="utf-8"))
    expected = _expected_top_key(snippet.stem)
    assert expected in data, (
        f"{snippet.name}: expected top-level key '{expected}', "
        f"found keys: {list(data.keys())}"
    )
