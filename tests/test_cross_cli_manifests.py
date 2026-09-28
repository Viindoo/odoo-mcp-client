"""
Behavioral contract tests for the Codex CLI and Gemini CLI MCP manifests.

These tests verify that the derived manifest files correctly mirror the SSOT
(.mcp.json) and satisfy the structural requirements of each target runtime.

Rules tested (one intent per test, named after the business rule):
  1. gemini_extension_is_valid_json_with_three_servers
  2. gemini_extension_has_no_trust_key
  3. codex_plugin_json_has_all_required_interface_fields
  4. codex_plugin_json_mcpservers_points_to_relative_path
  5. codex_mcp_json_is_flat_with_three_servers
  6. all_derived_manifests_server_command_args_match_ssot
  7. local_servers_are_claude_only_and_absent_from_derived_manifests
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"

SSOT_MCP = PLUGIN_ROOT / ".mcp.json"
GEMINI_OUT = PLUGIN_ROOT / "gemini-extension.json"
CODEX_PLUGIN_JSON = PLUGIN_ROOT / ".codex-plugin" / "plugin.json"
CODEX_MCP_JSON = PLUGIN_ROOT / ".codex-plugin" / "mcp.json"

# The EAGER browser MCP server bundled in every runtime manifest. Only ONE family
# is eager (the headless chrome-devtools); the other five are OPT-IN, wired on
# demand by the odoo-setup steps and asserted in test_setup_wiring.py - they are
# deliberately NOT in the derived Codex/Gemini bundles (which mirror the SSOT
# .mcp.json), so a plain session never eager-loads six browser processes.
EXPECTED_SERVERS = {"chrome-devtools"}


def _local_servers() -> frozenset:
    """scripts/lib/plugin_mcp_servers.py LOCAL_SERVERS - the SSOT for which bundled
    .mcp.json servers are Claude-only and must never reach the derived Codex/Gemini
    manifests (their command/args reference ${CLAUDE_PLUGIN_ROOT}, which only Claude
    Code resolves)."""
    spec = importlib.util.spec_from_file_location(
        "plugin_mcp_servers", PLUGIN_ROOT / "scripts" / "lib" / "plugin_mcp_servers.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.LOCAL_SERVERS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def ssot_servers() -> dict:
    """Load the SSOT MCP server definitions (stripped of 'type' field), EXCLUDING
    any LOCAL (Claude-only) server. A local server is deliberately absent from the
    derived Codex/Gemini manifests (see gen_mcp_manifests.py and rule 7 below), so
    including it here would make rule 6 fail on an exclusion that is correct by
    design, not a real SSOT/manifest drift."""
    assert SSOT_MCP.is_file(), f"SSOT missing: {SSOT_MCP}"
    data = json.loads(SSOT_MCP.read_text(encoding="utf-8"))
    raw = data.get("mcpServers", data)
    local = _local_servers()
    return {
        name: {k: v for k, v in entry.items() if k != "type"}
        for name, entry in raw.items()
        if name not in local
    }


@pytest.fixture(scope="module")
def gemini_data() -> dict:
    assert GEMINI_OUT.is_file(), f"gemini-extension.json missing: {GEMINI_OUT}"
    return json.loads(GEMINI_OUT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def codex_plugin_data() -> dict:
    assert CODEX_PLUGIN_JSON.is_file(), f".codex-plugin/plugin.json missing: {CODEX_PLUGIN_JSON}"
    return json.loads(CODEX_PLUGIN_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def codex_mcp_data() -> dict:
    assert CODEX_MCP_JSON.is_file(), f".codex-plugin/mcp.json missing: {CODEX_MCP_JSON}"
    return json.loads(CODEX_MCP_JSON.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Rule 1: gemini-extension.json is valid JSON with all 3 servers
# ---------------------------------------------------------------------------

def test_gemini_extension_is_valid_json_with_three_servers(gemini_data):
    """gemini-extension.json must be parseable JSON containing the eager browser MCP server."""
    servers = gemini_data.get("mcpServers", {})
    missing = EXPECTED_SERVERS - set(servers.keys())
    assert not missing, (
        f"gemini-extension.json is missing servers: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Rule 2: gemini-extension.json must not contain a 'trust' key anywhere
# ---------------------------------------------------------------------------

def _has_trust_key(obj, path="root") -> list[str]:
    """Recursively find any 'trust' key in a nested dict/list structure."""
    hits = []
    if isinstance(obj, dict):
        if "trust" in obj:
            hits.append(path)
        for k, v in obj.items():
            hits.extend(_has_trust_key(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            hits.extend(_has_trust_key(item, f"{path}[{i}]"))
    return hits


def test_gemini_extension_has_no_trust_key(gemini_data):
    """Gemini extension manifests must not include a 'trust' key anywhere (forbidden field)."""
    hits = _has_trust_key(gemini_data)
    assert not hits, (
        f"gemini-extension.json contains forbidden 'trust' key at: {hits}"
    )


# ---------------------------------------------------------------------------
# Rule 3: .codex-plugin/plugin.json has all required interface fields
# ---------------------------------------------------------------------------

REQUIRED_INTERFACE_FIELDS = [
    "displayName",
    "shortDescription",
    "longDescription",
    "developerName",
    "category",
    "websiteURL",
    "privacyPolicyURL",
    "termsOfServiceURL",
]

REQUIRED_TOP_FIELDS = ["name", "version", "description", "author", "homepage", "license"]


def test_codex_plugin_json_has_all_required_interface_fields(codex_plugin_data):
    """
    .codex-plugin/plugin.json must have all required top-level and interface fields,
    and every field must be non-empty.
    """
    for field in REQUIRED_TOP_FIELDS:
        assert field in codex_plugin_data, f".codex-plugin/plugin.json missing top-level field '{field}'"
        val = codex_plugin_data[field]
        assert val, f".codex-plugin/plugin.json field '{field}' is empty"

    assert "interface" in codex_plugin_data, ".codex-plugin/plugin.json missing 'interface' object"
    iface = codex_plugin_data["interface"]
    for field in REQUIRED_INTERFACE_FIELDS:
        assert field in iface, f".codex-plugin/plugin.json interface missing field '{field}'"
        assert str(iface[field]).strip(), f".codex-plugin/plugin.json interface.{field} is empty"


# ---------------------------------------------------------------------------
# Rule 4: .codex-plugin/plugin.json mcpServers pointer is a relative path
# ---------------------------------------------------------------------------

def test_codex_plugin_json_mcpservers_points_to_relative_path(codex_plugin_data):
    """mcpServers in .codex-plugin/plugin.json must be a relative pointer to ./mcp.json."""
    assert "mcpServers" in codex_plugin_data, ".codex-plugin/plugin.json missing 'mcpServers'"
    val = codex_plugin_data["mcpServers"]
    assert val == "./mcp.json", (
        f"mcpServers must be './mcp.json' (relative to .codex-plugin/); got '{val}'"
    )


# ---------------------------------------------------------------------------
# Rule 5: .codex-plugin/mcp.json is flat (no mcpServers wrapper) with 3 servers
# ---------------------------------------------------------------------------

def test_codex_mcp_json_is_flat_with_three_servers(codex_mcp_data):
    """
    .codex-plugin/mcp.json must be flat (no top-level 'mcpServers' wrapper) and
    contain the eager browser MCP server.
    """
    assert "mcpServers" not in codex_mcp_data, (
        ".codex-plugin/mcp.json must be flat (no 'mcpServers' wrapper key); "
        "Codex expects server entries at the top level."
    )
    missing = EXPECTED_SERVERS - set(codex_mcp_data.keys())
    assert not missing, (
        f".codex-plugin/mcp.json is missing servers: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Rule 6: All derived manifests' server command+args match the SSOT
# ---------------------------------------------------------------------------

def test_all_derived_manifests_server_command_args_match_ssot(
    ssot_servers, gemini_data, codex_mcp_data
):
    """
    Every server entry in gemini-extension.json and .codex-plugin/mcp.json must have
    the same command and args as the SSOT .mcp.json (after stripping 'type').
    """
    gemini_servers = gemini_data.get("mcpServers", {})
    mismatches = []

    for server_name, expected in ssot_servers.items():
        for manifest_label, manifest_servers in [
            ("gemini-extension.json", gemini_servers),
            (".codex-plugin/mcp.json", codex_mcp_data),
        ]:
            if server_name not in manifest_servers:
                mismatches.append(f"{manifest_label}: missing server '{server_name}'")
                continue
            actual = manifest_servers[server_name]
            if actual.get("command") != expected.get("command"):
                mismatches.append(
                    f"{manifest_label}.{server_name}: command mismatch "
                    f"(expected {expected.get('command')!r}, got {actual.get('command')!r})"
                )
            if actual.get("args") != expected.get("args"):
                mismatches.append(
                    f"{manifest_label}.{server_name}: args mismatch "
                    f"(expected {expected.get('args')!r}, got {actual.get('args')!r})"
                )
            # 'type' must not appear in derived manifests (Codex/Gemini infer from command)
            if "type" in actual:
                mismatches.append(
                    f"{manifest_label}.{server_name}: must not contain 'type' field "
                    f"(got {actual['type']!r})"
                )

    assert not mismatches, (
        "Derived manifest server entries diverge from SSOT (.mcp.json):\n"
        + "\n".join(f"  - {m}" for m in mismatches)
    )


# ---------------------------------------------------------------------------
# Rule 7: LOCAL (Claude-only) servers never reach the derived manifests
# ---------------------------------------------------------------------------

def test_local_servers_are_claude_only_and_absent_from_derived_manifests(gemini_data, codex_mcp_data):
    """A LOCAL server (e.g. odoo-local) is bundled in the SSOT .mcp.json but its command/args
    reference ${CLAUDE_PLUGIN_ROOT}, which only Claude Code resolves - forwarding it to the
    Codex/Gemini manifests would ship an entry neither runtime could ever launch. Assert the
    premise (it really is in .mcp.json) AND the exclusion (it is absent from both derived
    manifests) so this test cannot pass by accident if the premise ever stops holding."""
    local = _local_servers()

    raw = json.loads(SSOT_MCP.read_text(encoding="utf-8")).get("mcpServers", {})
    present_in_ssot = local & set(raw)
    assert present_in_ssot, (
        f"premise failed: none of the local servers {sorted(local)} are in .mcp.json "
        f"(got {sorted(raw)}) - this test would otherwise pass vacuously"
    )

    gemini_servers = set(gemini_data.get("mcpServers", {}).keys())
    codex_servers = set(codex_mcp_data.keys())
    for server in present_in_ssot:
        assert server not in gemini_servers, (
            f"local server {server!r} leaked into gemini-extension.json (Gemini cannot resolve "
            "${CLAUDE_PLUGIN_ROOT})"
        )
        assert server not in codex_servers, (
            f"local server {server!r} leaked into .codex-plugin/mcp.json (Codex cannot resolve "
            "${CLAUDE_PLUGIN_ROOT})"
        )
