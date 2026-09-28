"""The odoo-local tool surface and the prose that points at it agree, in both directions.

Tool names, descriptions and schemas live in the server (scripts/mcp/odoo_local/tools_*.py) and are
the agents' only usage documentation. Agent-facing prose (agents, skills, snippets, commands,
workflows, docs) names those tools. Contracts protected:

  - every tool name the prose mentions is a tool the server registers: a renamed or removed tool
    cannot leave an agent calling something that does not exist;
  - every registered tool documents itself for an executing agent (a description of at least 80
    chars, a description on every input property);
  - every registered tool is listed in the human reference's tool index
    (docs/reference/INSTANCE-ALLOCATION-API.md), so a new tool cannot ship undocumented there.

A mention is either the full call form `mcp__plugin_odoo-ai-agents_odoo-local__<name>` (always a
tool reference) or a bare token of the tool-name vocabulary (lease_* / instance_* / catalog_* and
the singletons below). A bare token that is a DATA identifier rather than a tool - a schema field
of any registered tool (derived from the registry, e.g. `lease_token`, `instance_handle`) or one
of NON_TOOL_IDENTIFIERS (brief/placeholder field names declared in agent prose) - is not a tool
mention. Everything else in the vocabulary must be a registered tool.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from odoo_local_mcp_harness import PLUGIN, import_package

import_package()
from odoo_local import cli, protocol  # noqa: E402

PROSE_DIRS = ("agents", "skills", "snippets", "commands", "workflows", "docs")
PROSE_SUFFIXES = (".md", ".yaml", ".yml", ".json", ".txt")
REFERENCE_DOC = PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION-API.md"
CALL_PREFIX = "mcp__plugin_odoo-ai-agents_odoo-local__"

# Brief / placeholder field names agent prose declares that share the tool vocabulary's shape but
# name data, not a tool. Each must still occur in the prose (asserted below), so an exemption for a
# word nobody writes any more fails instead of lingering.
NON_TOOL_IDENTIFIERS = frozenset({
    "instance_base_url",    # odoo-ui-reviewer brief field: the served base URL
    "instance_base_url_b",  # its second-build twin
    "instance_login",       # odoo-ui-reviewer brief field: the login to use
    "instance_touching",    # gate-tier registry key (generator/skill_tool_deps.json, run-harness)
    "instance_id",          # doc-plan.yaml field naming one planned instance
})

_FAMILY = r"(?:lease|instance|catalog)_[a-z][a-z0-9_]*"
_SINGLETONS = r"(?:job_wait|series_detect|project_dir|db_preflight|server_info)"
# (?<![\w-]) / (?![\w-]): the token is not part of a longer identifier or a hyphenated name
# (odoo_instance_ops, instances_io, release_lock, odoo-local-x ...). Case-sensitive on purpose:
# INSTANCE_HANDLE is the contract's name, not a tool.
BARE_RE = re.compile(r"(?<![\w-])(%s|%s)(?![\w-])" % (_FAMILY, _SINGLETONS))
FULL_RE = re.compile(re.escape(CALL_PREFIX) + r"([a-z][a-z0-9_]*)")


def mentions(text):
    """(full-form tool names, bare vocabulary tokens) mentioned in `text`."""
    full = set(FULL_RE.findall(text))
    stripped = FULL_RE.sub(" ", text)
    return full, set(BARE_RE.findall(stripped))


@pytest.fixture(scope="module")
def registry():
    ctx = protocol.ServerContext("t", cli.Anchor(1, None, None, "test"), PLUGIN)
    return protocol.build_registry(ctx)


def _schema_property_names(schema, out):
    if isinstance(schema, dict):
        for key, sub in (schema.get("properties") or {}).items():
            out.add(key)
            _schema_property_names(sub, out)
        for key in ("items", "additionalProperties"):
            _schema_property_names(schema.get(key), out)
        for sub in schema.get("anyOf") or ():
            _schema_property_names(sub, out)
    return out


@pytest.fixture(scope="module")
def data_identifiers(registry):
    names = set()
    for name in registry.names():
        tool = registry.get(name)
        _schema_property_names(tool.input_schema, names)
        _schema_property_names(tool.output_schema, names)
    return names


@pytest.fixture(scope="module")
def prose():
    files = {}
    for d in PROSE_DIRS:
        for path in sorted((PLUGIN / d).rglob("*")):
            if path.is_file() and path.suffix in PROSE_SUFFIXES:
                files[path] = path.read_text(encoding="utf-8", errors="replace")
    assert files, "no prose found - the scan roots moved"
    return files


# --------------------------------------------------------------------------- #
# the matcher itself
# --------------------------------------------------------------------------- #
def test_matcher_finds_every_mention_shape():
    text = ("call `lease_acquire` first, then lease_find(state parked); wait with job_wait. "
            "Use mcp__plugin_odoo-ai-agents_odoo-local__instance_serve to serve. "
            "series_detect, project_dir, db_preflight, server_info, catalog_read.")
    full, bare = mentions(text)
    assert full == {"instance_serve"}
    assert bare == {"lease_acquire", "lease_find", "job_wait", "series_detect", "project_dir",
                    "db_preflight", "server_info", "catalog_read"}


@pytest.mark.parametrize("text", [
    "agents/odoo_instance_ops.md", "scripts/lib/instances_io.py", "the INSTANCE_HANDLE contract",
    "release_lock(token)", "nolease_acquire", "odoo-instance-ops", "lease-acquire", "Lease_acquire",
    "the release_job and my_project_dir and xjob_wait", "catalog-read",
])
def test_matcher_ignores_words_that_only_contain_the_vocabulary(text):
    assert mentions(text) == (set(), set())


def test_a_full_form_mention_is_not_double_counted_as_a_bare_token():
    full, bare = mentions("`mcp__plugin_odoo-ai-agents_odoo-local__lease_release`")
    assert full == {"lease_release"} and bare == set()


# --------------------------------------------------------------------------- #
# prose -> registry
# --------------------------------------------------------------------------- #
def test_every_tool_the_prose_names_is_registered(registry, data_identifiers, prose):
    tools = set(registry.names())
    dangling = []
    for path, text in prose.items():
        full, bare = mentions(text)
        rel = path.relative_to(PLUGIN)
        dangling += ["%s: %s%s" % (rel, CALL_PREFIX, n) for n in sorted(full - tools)]
        unknown = bare - tools - data_identifiers - NON_TOOL_IDENTIFIERS
        dangling += ["%s: %s" % (rel, n) for n in sorted(unknown)]
    assert not dangling, "prose names odoo-local tools the server does not register:\n" + "\n".join(dangling)


def test_every_non_tool_exemption_is_still_written_and_is_not_a_tool(registry, prose):
    seen = set()
    for text in prose.values():
        seen |= mentions(text)[1]
    assert not NON_TOOL_IDENTIFIERS & set(registry.names()), "an exempted word became a real tool"
    unused = sorted(NON_TOOL_IDENTIFIERS - seen)
    assert not unused, "exemptions nobody writes any more (drop them): %s" % unused


# --------------------------------------------------------------------------- #
# registry: self-documenting, and indexed in the reference
# --------------------------------------------------------------------------- #
def test_every_tool_is_documented_for_an_executing_agent(registry):
    for name in registry.names():
        tool = registry.get(name)
        assert len(tool.description.strip()) >= 80, name
        for prop, sub in (tool.input_schema.get("properties") or {}).items():
            assert (sub.get("description") or "").strip(), "%s.%s has no description" % (name, prop)


def test_every_tool_is_listed_in_the_reference_tool_index(registry):
    indexed = set(re.findall(r"^\|\s*`([a-z][a-z0-9_]*)`\s*\|", REFERENCE_DOC.read_text(encoding="utf-8"),
                             re.MULTILINE))
    missing = sorted(set(registry.names()) - indexed)
    assert not missing, "tools missing from the %s tool index: %s" % (REFERENCE_DOC.name, missing)
    stale = sorted(n for n in indexed - set(registry.names()) if BARE_RE.fullmatch(n))
    assert not stale, "the tool index lists tools the server no longer registers: %s" % stale
