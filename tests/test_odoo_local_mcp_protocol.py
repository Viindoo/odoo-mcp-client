"""Behavior tests for the odoo-local stdio MCP server: the wire protocol, argument validation, the
error contract, the session anchor it exports to children, and the stdio discipline.

Protocol-level cases drive the REAL entry point over pipes (tests/odoo_local_mcp_harness.py);
unit-level cases import the package to reach seams a live server cannot (a slow tool, the degraded
PYTHON_TOO_OLD loop, the allocator envelope parser).
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from odoo_local_mcp_harness import (
    LIB_DIR, MCP_DIR, PACKAGE, PLUGIN, SERVER, McpClient, hermetic_env, import_package, structured,
)

pkg = import_package()
from odoo_local import cli, errors, protocol  # noqa: E402

PLUGIN_VERSION = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]


@pytest.fixture
def server(tmp_path):
    with McpClient(hermetic_env(tmp_path / "home"), tmp_path) as client:
        yield client


@pytest.fixture
def ready(server):
    server.initialize()
    return server


# --------------------------------------------------------------------------- #
# initialize / lifecycle
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("version", ["2025-06-18", "2025-03-26", "2024-11-05"])
def test_initialize_echoes_a_supported_client_protocol_version(server, version):
    result = server.initialize(version)["result"]
    assert result["protocolVersion"] == version


def test_initialize_answers_latest_supported_for_an_unknown_version(server):
    result = server.initialize("1999-01-01")["result"]
    assert result["protocolVersion"] == "2025-06-18"


def test_initialize_reports_identity_capabilities_and_scope(server):
    result = server.initialize()["result"]
    assert result["serverInfo"] == {"name": "odoo-local", "version": PLUGIN_VERSION}
    assert result["capabilities"] == {"tools": {"listChanged": False}}
    text = result["instructions"]
    # Agent-facing scope statement: live local lifecycle, explicitly NOT the source index.
    assert "Odoo Semantic" in text and "NOT the Odoo source index" in text
    assert "instances.toml" in text and "lease" in text
    assert len(text) < 600, "instructions must stay short"


def test_notifications_get_no_reply(ready):
    ready.notify("notifications/initialized")
    ready.notify("notifications/some-unknown-notification")
    rid = ready.request_async("ping")
    first = ready.next_message()
    assert first.get("id") == rid and first["result"] == {}


def test_server_exits_cleanly_on_stdin_eof(tmp_path):
    client = McpClient(hermetic_env(tmp_path / "home"), tmp_path)
    client.initialize()
    client.close()
    assert client.proc.returncode == 0


# --------------------------------------------------------------------------- #
# protocol errors
# --------------------------------------------------------------------------- #
def test_malformed_json_is_parse_error_and_server_survives(ready):
    ready.send_raw("{not json")
    msg = ready.next_message()
    assert msg["id"] is None and msg["error"]["code"] == -32700
    assert ready.request("ping")["result"] == {}


def test_unknown_method_is_method_not_found(ready):
    resp = ready.request("resources/list")
    assert resp["error"]["code"] == -32601
    assert "resources/list" in resp["error"]["message"]


@pytest.mark.parametrize("payload", [
    {"id": 99, "method": "ping"},                          # no jsonrpc member
    {"jsonrpc": "2.0", "id": 99, "method": 5},             # non-string method
])
def test_malformed_request_is_invalid_request(ready, payload):
    ready.send(payload)
    msg = ready.wait_for(99)
    assert msg["error"]["code"] == -32600


def test_batch_is_rejected_as_invalid_request(ready):
    ready.send([{"jsonrpc": "2.0", "id": 7, "method": "ping"}])
    msg = ready.next_message()
    assert msg["id"] is None and msg["error"]["code"] == -32600


@pytest.mark.parametrize("params,needle", [
    ({"name": "no_such_tool", "arguments": {}}, "no_such_tool"),
    ({"arguments": {}}, "name"),
    ({"name": "server_info", "arguments": [1, 2]}, "arguments"),
])
def test_bad_tools_call_params_are_invalid_params(ready, params, needle):
    resp = ready.request("tools/call", params)
    assert resp["error"]["code"] == -32602
    assert needle in resp["error"]["message"]


def test_non_object_params_are_invalid_params(ready):
    resp = ready.request("tools/list", [1])
    assert resp["error"]["code"] == -32602


# --------------------------------------------------------------------------- #
# tools/list contract
# --------------------------------------------------------------------------- #
def test_every_tool_is_fully_described(ready):
    tools = ready.request("tools/list")["result"]["tools"]
    names = [t["name"] for t in tools]
    assert {"server_info", "catalog_read", "catalog_locate", "series_detect", "project_dir"} <= set(names)
    assert len(names) == len(set(names))
    for tool in tools:
        assert tool["description"].strip(), tool["name"]
        schema = tool["inputSchema"]
        assert schema["type"] == "object" and schema.get("additionalProperties") is False, tool["name"]
        for prop, sub in schema.get("properties", {}).items():
            assert sub.get("description"), "%s.%s has no description" % (tool["name"], prop)
        out = tool["outputSchema"]
        assert out["type"] == "object" and len(out["anyOf"]) == 2, tool["name"]
        assert "annotations" in tool and isinstance(tool["annotations"]["readOnlyHint"], bool)


def test_no_tool_name_collides_with_browser_hook_vocabulary(ready):
    # The teardown/permission hooks count browser pages and recordings by these name shapes.
    tools = ready.request("tools/list")["result"]["tools"]
    for tool in tools:
        name = tool["name"]
        assert not name.startswith("browser_"), name
        for suffix in ("new_page", "close_page", "record_page", "stop_recording"):
            assert not name.endswith(suffix), name


@pytest.mark.parametrize("bad", ["browser_open", "x_new_page", "close_page", "a_record_page",
                                 "stop_recording", "Upper", "has-dash", ""])
def test_registry_refuses_reserved_or_malformed_names(bad):
    reg = protocol.ToolRegistry()
    with pytest.raises(ValueError):
        reg.add(bad, "d", {"type": "object"}, {"type": "object"}, lambda a, c: {})


def test_registry_refuses_duplicates_and_missing_description():
    reg = protocol.ToolRegistry()
    reg.add("one", "d", {"type": "object"}, {"type": "object"}, lambda a, c: {})
    with pytest.raises(ValueError):
        reg.add("one", "d", {"type": "object"}, {"type": "object"}, lambda a, c: {})
    with pytest.raises(ValueError):
        reg.add("two", "  ", {"type": "object"}, {"type": "object"}, lambda a, c: {})


# --------------------------------------------------------------------------- #
# tools/call: argument validation + result shapes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tool,args,field", [
    ("catalog_read", {"series": 17}, "arguments.series"),
    ("catalog_read", {"bogus": "x"}, "arguments.bogus"),
    ("series_detect", {}, "arguments.path"),
    ("project_dir", {"cwd": "/", "axis": "sideways"}, "arguments.axis"),
    ("project_dir", {"axis": "share"}, "arguments.cwd"),
    ("catalog_locate", {"path": ""}, "arguments.path"),
])
def test_invalid_arguments_are_a_tool_error_naming_the_field(ready, tool, args, field):
    result = ready.call(tool, args)
    assert result["isError"] is True
    err = structured(result)["error"]
    assert err["code"] == "INVALID_ARGUMENTS"
    assert err["message"].startswith(field), err["message"]
    assert err["remedy"] == errors.SERVER_CODES["INVALID_ARGUMENTS"]
    assert isinstance(err["diagnostics"], dict)


def test_relative_path_is_rejected_by_name(ready):
    err = structured(ready.call("series_detect", {"path": "relative/dir"}))["error"]
    assert err["code"] == "INVALID_ARGUMENTS" and "arguments.path" in err["message"]


def test_success_result_carries_structured_content_and_matching_text(ready):
    result = ready.call("server_info", {})
    assert result["isError"] is False
    info = structured(result)
    assert info["name"] == "odoo-local" and info["version"] == PLUGIN_VERSION
    assert Path(info["plugin_root"]) == PLUGIN.resolve()


def test_omitted_arguments_mean_empty_object(ready):
    assert ready.call("server_info")["isError"] is False


# --------------------------------------------------------------------------- #
# session anchor
# --------------------------------------------------------------------------- #
def _session_anchor():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sa_under_test", LIB_DIR / "session_anchor.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_server_anchors_on_the_nearest_agent_cli_ancestor_else_its_parent(ready):
    anchor = structured(ready.call("server_info"))["anchor"]
    # The test process is the server's parent. When the suite itself runs inside an agent session,
    # the nearest agent-CLI ancestor is the session; otherwise the parent is.
    sa = _session_anchor()
    expected = sa._ancestor_anchor(os.getpid()) or os.getpid()
    assert anchor["pid"] == expected
    assert anchor["fingerprint"] == (sa.fingerprint(expected) or "")
    assert anchor["exported"] is bool(anchor["fingerprint"])


def test_server_reports_the_session_id_it_was_started_with(tmp_path):
    env = hermetic_env(tmp_path / "home", CLAUDE_CODE_SESSION_ID="sess-123")
    with McpClient(env, tmp_path) as client:
        client.initialize()
        assert structured(client.call("server_info"))["anchor"]["session_id"] == "sess-123"


def test_children_inherit_anchor_and_via(tmp_path, monkeypatch):
    monkeypatch.delenv("ODOO_AI_SESSION_ANCHOR", raising=False)
    rc, out, _ = cli.run([sys.executable, "-c",
                          "import os, json; print(json.dumps({k: os.environ.get(k) for k in "
                          "('ODOO_AI_SESSION_ANCHOR', 'ODOO_AI_VIA')}))"], tmp_path, 30)
    assert rc == 0
    seen = json.loads(out)
    assert seen["ODOO_AI_VIA"] == "mcp"
    anchor = cli.anchor()
    expected = _session_anchor().format_anchor(anchor.pid, anchor.fingerprint) if anchor.fingerprint else None
    assert seen["ODOO_AI_SESSION_ANCHOR"] == expected
    if expected:
        sa = _session_anchor()
        assert sa.parse_anchor(expected) == (sa._ancestor_anchor(os.getppid()) or os.getppid(), anchor.fingerprint)


def test_operator_anchor_opt_out_is_propagated_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("ODOO_AI_SESSION_ANCHOR", "none")
    rc, out, _ = cli.run([sys.executable, "-c", "import os; print(os.environ['ODOO_AI_SESSION_ANCHOR'])"], tmp_path, 30)
    assert rc == 0 and out.strip() == "none"
    assert cli.anchor().as_dict()["exported"] is False


def test_anchor_constants_agree_with_session_anchor():
    sa = _session_anchor()
    assert cli.ANCHOR_ENV == sa.ANCHOR_ENV
    assert cli.ANCHOR_DISABLED == sa.ANCHOR_DISABLED
    assert cli.SESSION_ID_ENV == sa.SESSION_ID_ENV


# --------------------------------------------------------------------------- #
# subprocess boundary
# --------------------------------------------------------------------------- #
def test_run_requires_an_existing_cwd(tmp_path):
    with pytest.raises(NotADirectoryError):
        cli.run(["true"], tmp_path / "missing", 5)


def test_run_timeout_kills_the_whole_process_group(tmp_path):
    marker = tmp_path / "grandchild.pid"
    start = time.monotonic()
    with pytest.raises(cli.SubprocessTimeout):
        cli.run(["bash", "-c", "sleep 30 & echo $! > %s; wait" % marker], tmp_path, 1)
    assert time.monotonic() - start < 10
    time.sleep(0.3)
    grandchild = int(marker.read_text().strip())
    with pytest.raises(ProcessLookupError):
        os.kill(grandchild, 0)


def test_run_plugin_script_refuses_paths_outside_the_plugin(tmp_path):
    with pytest.raises(ValueError):
        cli.run_plugin_script("../../etc/passwd", [], tmp_path, 5)


# --------------------------------------------------------------------------- #
# allocator JSON envelope (documented contract; allocator itself is exercised elsewhere)
# --------------------------------------------------------------------------- #
def test_envelope_success_is_returned_with_fields():
    env = cli.parse_allocator_envelope(0, '{"ok":true,"rc":0,"error":null,"fields":{"ALLOC_TOKEN":"t1"}}', "")
    assert env["ok"] is True and env["fields"] == {"ALLOC_TOKEN": "t1"}


def test_envelope_is_found_after_stray_stdout_lines():
    out = 'warming up\n{"ok":true,"rc":0,"error":null,"fields":{}}\n'
    assert cli.parse_allocator_envelope(0, out, "")["ok"] is True


@pytest.mark.parametrize("stdout", ["", "ALLOC_TOKEN=x", '{"rc":0}', '{"ok":"yes"}', '{"ok":false,"rc":3}'])
def test_envelope_absent_or_malformed_is_an_error(stdout):
    with pytest.raises(cli.AllocatorEnvelopeError):
        cli.parse_allocator_envelope(3, stdout, "")


def _stub_allocator(tmp_path, body):
    stub = tmp_path / "allocator_stub.py"
    stub.write_text("import json, sys\nargv = sys.argv[1:]\n" + body)
    return stub


def test_run_allocator_appends_format_json_and_returns_the_envelope(tmp_path):
    stub = _stub_allocator(tmp_path, "print(json.dumps({'ok': True, 'rc': 0, 'error': None, 'fields': {'argv': argv}}))\n")
    env = cli.run_allocator("list", ["--session", "mine"], tmp_path, 30, script=stub)
    assert env["fields"]["argv"] == ["list", "--session", "mine", "--format", "json"]


def test_run_allocator_failure_keeps_the_allocator_code(tmp_path):
    stub = _stub_allocator(tmp_path, "print(json.dumps({'ok': False, 'rc': 5, 'error': {'code': 'NOT_OWNER', 'message': 'lease t1 is not yours'}, 'fields': {}}))\nsys.exit(5)\n")
    with pytest.raises(errors.ToolError) as info:
        cli.run_allocator("release", ["t1"], tmp_path, 30, script=stub)
    payload = info.value.payload()["error"]
    assert payload["code"] == "NOT_OWNER" and payload["message"] == "lease t1 is not yours"
    assert payload["diagnostics"]["rc"] == 5
    assert payload["remedy"] == errors.remedy_for("NOT_OWNER")


def test_run_allocator_without_envelope_is_output_invalid(tmp_path):
    stub = _stub_allocator(tmp_path, "print('ALLOC_TOKEN=abc')\n")
    with pytest.raises(errors.ToolError) as info:
        cli.run_allocator("acquire", [], tmp_path, 30, script=stub)
    assert info.value.code == "ALLOCATOR_OUTPUT_INVALID"
    assert "ALLOC_TOKEN=abc" in info.value.diagnostics["stdout"]


# --------------------------------------------------------------------------- #
# error table
# --------------------------------------------------------------------------- #
def test_every_server_code_has_a_one_line_imperative_remedy():
    for code, remedy in errors.SERVER_CODES.items():
        assert code.isupper() and remedy.strip() and "\n" not in remedy, code


def test_unknown_code_gets_the_fallback_remedy():
    assert errors.remedy_for("SOMETHING_NEW") == errors.FALLBACK_REMEDY


def test_allocator_table_merges_and_server_codes_win(monkeypatch):
    # Codes the translation layer does not re-word flow through with the allocator's remedy.
    monkeypatch.setattr(errors, "_allocator_cache", [errors._normalize_allocator_table({
        "SOME_NEW_ALLOCATOR_CODE": {"rc": 5, "remedy": "Release only a token you acquired."},
        "ANOTHER_NEW_CODE": "Pass --run-id.",
        "INVALID_ARGUMENTS": "allocator must not redefine this",
        "BROKEN": 42,
    })])
    table = errors.table()
    assert table["SOME_NEW_ALLOCATOR_CODE"] == "Release only a token you acquired."
    assert table["ANOTHER_NEW_CODE"] == "Pass --run-id."
    assert table["INVALID_ARGUMENTS"] == errors.SERVER_CODES["INVALID_ARGUMENTS"]
    assert "BROKEN" not in table


def test_tool_vocabulary_translation_overrides_the_allocator_cli_wording(monkeypatch):
    """An agent calling tools cannot pass allocator CLI flags, so a translated code's remedy is
    the tool-vocabulary one - the allocator's CLI wording never reaches the agent."""
    monkeypatch.setattr(errors, "_allocator_cache", [errors._normalize_allocator_table({
        "ADDONS_PATH_WORKTREE_MISMATCH": "pass --addons-path-override <the tree to build>",
    })])
    remedy = errors.table()["ADDONS_PATH_WORKTREE_MISMATCH"]
    assert remedy == errors.TOOL_REMEDIES["ADDONS_PATH_WORKTREE_MISMATCH"]
    assert "--addons-path-override" not in remedy and "addons_path" in remedy


def test_port_pool_exhausted_remedy_branches_on_the_allocator_reason():
    """PORT_POOL_EXHAUSTED carries ONE remedy table entry, split by fields.reason (errors.py module
    docstring): the ordinary holders-based remedy when there IS a holder to release/park (or no
    reason is reported at all), a DISTINCT one when the allocator names
    ports-busy-outside-registry (no lease holds the pool, so releasing one would be a false lead)."""
    entry = errors.TOOL_REMEDIES["PORT_POOL_EXHAUSTED"]
    assert isinstance(entry, dict) and set(entry) == {"default", "reasons"}

    holders_present = errors.remedy_for("PORT_POOL_EXHAUSTED", {"fields": {"holders": [{"token": "t1"}]}})
    assert holders_present == entry["default"]
    assert "release" in holders_present.lower()

    no_diagnostics = errors.remedy_for("PORT_POOL_EXHAUSTED")
    assert no_diagnostics == entry["default"]

    busy_outside = errors.remedy_for("PORT_POOL_EXHAUSTED",
                                     {"fields": {"reason": "ports-busy-outside-registry", "holders": []}})
    assert busy_outside == entry["reasons"]["ports-busy-outside-registry"]
    assert busy_outside != entry["default"]
    assert "outside the lease registry" in busy_outside
    assert "release or park a lease" not in busy_outside


def test_venv_missing_remedy_names_an_absolute_doc_path():
    remedy = errors.SERVER_CODES["VENV_MISSING"]
    doc_path = PLUGIN / "snippets" / "venv-resolution.md"
    assert str(doc_path) in remedy
    assert doc_path.is_file(), "the remedy must name a doc that actually exists: %s" % doc_path
    assert " snippets/venv-resolution.md" not in remedy, "no relative doc path left behind"


def test_tool_unavailable_remedy_names_an_absolute_doc_path():
    """A relative doc path in a remedy is meaningless to an agent whose cwd is a user project, not
    this plugin: the remedy must resolve to the doc's absolute path under the plugin root."""
    remedy = errors.SERVER_CODES["TOOL_UNAVAILABLE"]
    doc_path = PLUGIN / "docs" / "reference" / "INSTANCE-ALLOCATION-API.md"
    assert str(doc_path) in remedy
    assert doc_path.is_file(), "the remedy must name a doc that actually exists: %s" % doc_path


# --------------------------------------------------------------------------- #
# validator (the subset the schemas use)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value,schema,needle", [
    (5, {"type": "integer", "minimum": 10}, "below the minimum"),
    (600, {"type": "integer", "maximum": 540}, "above the maximum"),
    (True, {"type": "integer"}, "expected integer, got boolean"),
    (["a", 3], {"type": "array", "items": {"type": "string"}}, "arguments[1]"),
    ({"a": 1}, {"type": "object", "properties": {}, "additionalProperties": False}, "arguments.a: unknown field"),
    ("x", {"enum": ["a", "b"]}, "is not one of"),
    ("", {"type": "string", "minLength": 1}, "at least 1"),
    (3, {"anyOf": [{"type": "string"}, {"type": "null"}]}, "matches none"),
])
def test_validator_names_the_violation(value, schema, needle):
    msg = protocol.validate(value, schema)
    assert msg and needle in msg, msg


def test_validator_accepts_conforming_values():
    schema = {"type": "object", "required": ["n"], "additionalProperties": False,
              "properties": {"n": {"type": "integer", "minimum": 1, "maximum": 9},
                             "tags": {"type": "array", "items": {"type": "string"}},
                             "row": {"anyOf": [{"type": "object"}, {"type": "null"}]}}}
    assert protocol.validate({"n": 3, "tags": ["a"], "row": None}, schema) is None


def test_defaults_come_from_the_schema():
    schema = {"type": "object", "properties": {"dry_run": {"type": "boolean", "default": True}}}
    assert protocol.apply_defaults({}, schema) == {"dry_run": True}
    assert protocol.apply_defaults({"dry_run": False}, schema) == {"dry_run": False}


# --------------------------------------------------------------------------- #
# concurrency + output discipline (in-process server with test tools)
# --------------------------------------------------------------------------- #
class _Pipe:
    def __init__(self):
        r, w = os.pipe()
        self.reader = os.fdopen(r, "rb")
        self.writer = os.fdopen(w, "wb")


def _in_process_server(registry):
    ctx = protocol.ServerContext("t", cli.Anchor(1, None, None, "test"), PLUGIN)
    stdin, stdout = _Pipe(), _Pipe()
    srv = protocol.Server(registry, ctx, stdout.writer, max_workers=4)
    thread = threading.Thread(target=srv.serve, args=(stdin.reader,), daemon=True)
    thread.start()
    return stdin, stdout, thread


def _send(pipe, obj):
    pipe.writer.write((json.dumps(obj) + "\n").encode())
    pipe.writer.flush()


def test_slow_tool_call_does_not_block_ping_or_other_calls():
    release = threading.Event()
    reg = protocol.ToolRegistry()
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    reg.add("slow", "d", empty, {"type": "object"}, lambda a, c: (release.wait(10), {"done": True})[1])
    reg.add("fast", "d", empty, {"type": "object"}, lambda a, c: {"fast": True})
    stdin, stdout, thread = _in_process_server(reg)
    _send(stdin, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "slow"}})
    _send(stdin, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
    _send(stdin, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "fast"}})
    first = json.loads(stdout.reader.readline())
    second = json.loads(stdout.reader.readline())
    assert {first["id"], second["id"]} == {2, 3}
    release.set()
    third = json.loads(stdout.reader.readline())
    assert third["id"] == 1 and third["result"]["structuredContent"] == {"done": True}
    stdin.writer.close()
    thread.join(10)
    assert not thread.is_alive()


def test_concurrent_results_never_interleave_on_the_wire():
    reg = protocol.ToolRegistry()
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    reg.add("big", "d", empty, {"type": "object"}, lambda a, c: {"blob": "x" * 200000})
    stdin, stdout, thread = _in_process_server(reg)
    for i in range(20):
        _send(stdin, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": "big"}})
    seen = {json.loads(stdout.reader.readline())["id"] for _ in range(20)}
    assert seen == set(range(20))
    stdin.writer.close()
    thread.join(10)


def test_handler_crash_and_schema_drift_become_internal_tool_errors():
    reg = protocol.ToolRegistry()
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    reg.add("boom", "d", empty, {"type": "object"}, lambda a, c: 1 / 0)
    reg.add("drift", "d", empty, {"type": "object", "required": ["x"]}, lambda a, c: {"y": 1})
    ctx = protocol.ServerContext("t", cli.Anchor(1, None, None, "test"), PLUGIN)
    for name, needle in (("boom", "ZeroDivisionError"), ("drift", "outputSchema")):
        result = protocol.call_tool(reg.get(name), {}, ctx)
        assert result["isError"] is True
        err = result["structuredContent"]["error"]
        assert err["code"] == "INTERNAL" and needle in err["message"]


def test_stray_print_in_a_tool_never_reaches_the_wire(tmp_path):
    # The entry point's claim_stdout() re-points fd 1 at stderr: a print() AND a child process
    # writing to its inherited fd 1 must both land on stderr, leaving only protocol bytes on stdout.
    code = (
        "import subprocess, sys; sys.path.insert(0, %r)\n"
        "import odoo_local_server as s\n"
        "wire = s.claim_stdout()\n"
        "print('STRAY'); subprocess.call(['echo', 'STRAY_CHILD'])\n"
        "wire.write(b'{}\\n'); wire.flush()\n"
    ) % str(MCP_DIR)
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=30)
    assert proc.stdout == b"{}\n"
    assert b"STRAY" in proc.stderr and b"STRAY_CHILD" in proc.stderr


# --------------------------------------------------------------------------- #
# PYTHON_TOO_OLD degraded mode + syntax floor
# --------------------------------------------------------------------------- #
def test_degraded_mode_reports_python_too_old_with_remedy():
    sys.path.insert(0, str(MCP_DIR))
    import odoo_local_server

    stdin, stdout = _Pipe(), _Pipe()
    thread = threading.Thread(target=odoo_local_server.degraded_main, args=(stdin.reader, stdout.writer), daemon=True)
    thread.start()
    _send(stdin, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
    init = json.loads(stdout.reader.readline())["result"]
    assert "PYTHON_TOO_OLD" not in init["serverInfo"]["name"] and "DISABLED" in init["instructions"]
    _send(stdin, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [t["name"] for t in json.loads(stdout.reader.readline())["result"]["tools"]] == ["server_info"]
    _send(stdin, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "server_info"}})
    result = json.loads(stdout.reader.readline())["result"]
    assert result["isError"] is True
    err = result["structuredContent"]["error"]
    assert err["code"] == "PYTHON_TOO_OLD" and err["remedy"] == errors.SERVER_CODES["PYTHON_TOO_OLD"]
    stdin.writer.close()
    thread.join(10)


def _oldest_parse_version():
    for minor in range(4, 9):
        try:
            ast.parse("x = 1", feature_version=(3, minor))
            return (3, minor)
        except ValueError:
            continue
    return (3, 8)


@pytest.mark.parametrize("path", sorted(PACKAGE.glob("*.py")) + [SERVER], ids=lambda p: p.name)
def test_server_sources_parse_as_python_3_8(path):
    ast.parse(path.read_text(), filename=str(path), feature_version=(3, 8))


@pytest.mark.parametrize("path", [SERVER, PACKAGE / "errors.py", PACKAGE / "__init__.py"], ids=lambda p: p.name)
def test_degraded_mode_files_parse_on_the_oldest_supported_grammar(path):
    # These run BEFORE the version gate, so they must parse on interpreters below the floor.
    ast.parse(path.read_text(), filename=str(path), feature_version=_oldest_parse_version())
    tree = ast.parse(path.read_text())
    assert not any(isinstance(n, ast.JoinedStr) for n in ast.walk(tree)), "f-string in %s" % path.name


# --------------------------------------------------------------------------- #
# long waits never starve short calls
# --------------------------------------------------------------------------- #
def test_short_calls_answer_promptly_while_more_long_waits_than_workers_block():
    release = threading.Event()
    reg = protocol.ToolRegistry()
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    reg.add("long_wait", "d", empty, {"type": "object"},
            lambda a, c: (release.wait(30), {"done": True})[1], long_running=True)
    reg.add("short", "d", empty, {"type": "object"}, lambda a, c: {"short": True})
    stdin, stdout, thread = _in_process_server(reg)  # 4 short workers
    try:
        for i in range(12):  # more long waits than the short pool has workers
            _send(stdin, {"jsonrpc": "2.0", "id": 100 + i, "method": "tools/call", "params": {"name": "long_wait"}})
        started = time.monotonic()
        _send(stdin, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "short"}})
        first = json.loads(stdout.reader.readline())
        assert first["id"] == 1 and time.monotonic() - started < 5
    finally:
        release.set()
    ids = {json.loads(stdout.reader.readline())["id"] for _ in range(12)}
    assert ids == set(range(100, 112))
    stdin.writer.close()
    thread.join(10)


def test_a_lease_mutation_answers_promptly_while_forty_long_waits_block():
    """The live starvation: 32 job_waits filled a bounded long pool and a lease_release queued 39s
    behind them. A long call runs on a thread of its own, so it never waits for another to end."""
    release = threading.Event()
    reg = protocol.ToolRegistry()
    empty = {"type": "object", "properties": {}, "additionalProperties": False}
    reg.add("job_wait_like", "d", empty, {"type": "object"},
            lambda a, c: (release.wait(60), {"done": True})[1], long_running=True)
    reg.add("release_like", "d", empty, {"type": "object"}, lambda a, c: {"released": True}, long_running=True)
    reg.add("list_like", "d", empty, {"type": "object"}, lambda a, c: {"listed": True})
    stdin, stdout, thread = _in_process_server(reg)
    try:
        for i in range(40):
            _send(stdin, {"jsonrpc": "2.0", "id": 100 + i, "method": "tools/call",
                          "params": {"name": "job_wait_like"}})
        started = time.monotonic()
        _send(stdin, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "release_like"}})
        _send(stdin, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "list_like"}})
        answered = {json.loads(stdout.reader.readline())["id"] for _ in range(2)}
        assert answered == {1, 2} and time.monotonic() - started < 5
    finally:
        release.set()
    ids = {json.loads(stdout.reader.readline())["id"] for _ in range(40)}
    assert ids == set(range(100, 140))
    stdin.writer.close()
    thread.join(10)
    assert not thread.is_alive(), "EOF drains every in-flight long call, then the server returns"


def test_the_tools_that_can_block_or_probe_run_on_the_long_lane():
    registry = protocol.build_registry(protocol.ServerContext("t", cli.Anchor(1, None, None, "test"), PLUGIN))
    long_tools = {n for n in registry.names() if registry.get(n).long_running}
    assert {"job_wait", "lease_release", "lease_park", "lease_gc", "instance_serve", "lease_acquire",
            "instance_status", "db_preflight", "lease_find"} <= long_tools
    assert not long_tools & {"lease_list", "catalog_read", "server_info"}


# --------------------------------------------------------------------------- #
# anchor through a wrapper
# --------------------------------------------------------------------------- #
def test_a_server_started_through_a_wrapper_shell_anchors_on_the_agent_cli_not_the_wrapper(tmp_path):
    """`claude` -> `sh -c` -> server: the anchor is the `claude` process (the session), never the
    short-lived-looking wrapper between them."""
    fake_cli = tmp_path / "claude"
    fake_cli.write_text('#!/bin/bash\nsh -c \'"$0" "$1"; exit $?\' "%s" "%s"\n' % (sys.executable, SERVER),
                        encoding="utf-8")
    fake_cli.chmod(0o755)
    env = hermetic_env(tmp_path / "home")
    env.pop("CLAUDE_PID", None)
    proc = subprocess.Popen([str(fake_cli)], cwd=str(tmp_path), env=env, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        for msg in ({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "server_info"}}):
            proc.stdin.write((json.dumps(msg) + "\n").encode())
            proc.stdin.flush()
        replies = {}
        while 2 not in replies:
            line = proc.stdout.readline()
            assert line, "server exited early"
            m = json.loads(line)
            replies[m.get("id")] = m
        anchor = replies[2]["result"]["structuredContent"]["anchor"]
        assert anchor["pid"] == proc.pid, "anchored on the wrapper, not the agent CLI"
        assert anchor["source"] == "mcp-ancestor"
    finally:
        proc.stdin.close()
        proc.wait(timeout=15)


# --------------------------------------------------------------------------- #
# MCP spec conformance (2025-06-18): request ids, pagination, cancellation, annotations
# --------------------------------------------------------------------------- #
def test_a_request_with_a_null_id_is_rejected_not_answered_as_a_request(ready):
    # MCP basic/messages: "the ID MUST NOT be null". A null-id request is malformed, not a ping.
    ready.send({"jsonrpc": "2.0", "id": None, "method": "ping"})
    msg = ready.next_message()
    assert msg["id"] is None
    assert "error" in msg and msg["error"]["code"] == -32600, msg


def test_tools_list_rejects_a_cursor_it_never_issued(ready):
    # MCP pagination: an invalid cursor SHOULD be -32602. This server never issues a nextCursor,
    # so every cursor is one it did not issue - silently answering page one again would let a
    # client loop forever believing it paged.
    first = ready.request("tools/list")["result"]
    assert "nextCursor" not in first
    resp = ready.request("tools/list", {"cursor": "not-a-cursor-this-server-issued"})
    assert resp.get("error", {}).get("code") == -32602, resp


def _cancellable_registry(observed):
    reg = protocol.ToolRegistry()
    empty = {"type": "object", "properties": {}, "additionalProperties": False}

    def waits_for_cancel(args, ctx):
        observed["cancelled"] = protocol.cancel_event().wait(30)
        return {"waited": True}

    reg.add("waits", "d", empty, {"type": "object"}, waits_for_cancel, long_running=True)
    return reg


def test_a_cancelled_call_stops_waiting_and_gets_no_response():
    # MCP utilities/cancellation: the receiver SHOULD stop processing and NOT send a response.
    observed = {}
    stdin, stdout, thread = _in_process_server(_cancellable_registry(observed))
    _send(stdin, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "waits"}})
    _send(stdin, {"jsonrpc": "2.0", "method": "notifications/cancelled",
                  "params": {"requestId": 1, "reason": "user interrupt"}})
    _send(stdin, {"jsonrpc": "2.0", "id": 2, "method": "ping"})
    started = time.monotonic()
    assert json.loads(stdout.reader.readline())["id"] == 2
    deadline = time.monotonic() + 5
    while "cancelled" not in observed and time.monotonic() < deadline:
        time.sleep(0.05)
    assert observed.get("cancelled") is True and time.monotonic() - started < 5
    _send(stdin, {"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert json.loads(stdout.reader.readline())["id"] == 3, "the cancelled call must never be answered"
    stdin.writer.close()
    thread.join(10)
    assert not thread.is_alive()


def test_cancel_event_outside_a_call_is_never_set():
    assert protocol.cancel_event().is_set() is False


def test_stdin_eof_stops_cancellable_waits_so_the_server_exits_promptly():
    # Claude Code closes stdin to shut a stdio server down; a job_wait-style wait must not hold
    # the process alive for its whole timeout after its client is gone.
    observed = {}
    stdin, stdout, thread = _in_process_server(_cancellable_registry(observed))
    _send(stdin, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "waits"}})
    started = time.monotonic()
    stdin.writer.close()
    thread.join(10)
    assert not thread.is_alive() and time.monotonic() - started < 5
    assert observed.get("cancelled") is True


def test_job_wait_returns_early_when_its_call_is_cancelled(tmp_path, monkeypatch):
    from odoo_local import jobs, tools_instance

    monkeypatch.setenv("ODOO_AI_HOME", str(tmp_path / "home"))
    job = jobs.start(["sleep", "30"], str(tmp_path))
    job_id = job["job_id"] if isinstance(job, dict) else job
    try:
        cancel = threading.Event()
        cancel.set()
        monkeypatch.setattr(protocol, "cancel_event", lambda: cancel)
        started = time.monotonic()
        ctx = protocol.ServerContext("t", cli.Anchor(1, None, None, "test"), PLUGIN)
        tools_instance._job_wait({"job_id": job_id, "timeout_s": 20}, ctx)
        assert time.monotonic() - started < 5
    finally:
        jobs.stop(job_id, grace_s=1)


def test_every_tool_is_annotated_as_local_and_classifies_its_destructiveness(ready):
    # Spec defaults are openWorldHint=true and, for a non-read-only tool, destructiveHint=true.
    # This server touches only this machine, and only the teardown tools can destroy anything.
    tools = {t["name"]: t for t in ready.request("tools/list")["result"]["tools"]}
    for name, tool in tools.items():
        ann = tool["annotations"]
        assert ann.get("openWorldHint") is False, name
        if ann["readOnlyHint"]:
            assert "destructiveHint" not in ann, name
        else:
            assert isinstance(ann.get("destructiveHint"), bool), "%s must classify destructiveHint" % name
    for name in ("lease_release", "lease_park", "lease_gc"):
        assert tools[name]["annotations"]["destructiveHint"] is True, name
    for name in ("lease_acquire", "lease_adopt", "project_dir", "instance_serve"):
        assert tools[name]["annotations"]["destructiveHint"] is False, name


def test_degraded_mode_negotiates_the_protocol_version_instead_of_echoing_any():
    sys.path.insert(0, str(MCP_DIR))
    import odoo_local_server

    stdin, stdout = _Pipe(), _Pipe()
    thread = threading.Thread(target=odoo_local_server.degraded_main, args=(stdin.reader, stdout.writer), daemon=True)
    thread.start()
    _send(stdin, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "1999-01-01"}})
    assert json.loads(stdout.reader.readline())["result"]["protocolVersion"] == protocol.LATEST_PROTOCOL_VERSION
    _send(stdin, {"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
    assert json.loads(stdout.reader.readline())["result"]["protocolVersion"] == "2024-11-05"
    stdin.writer.close()
    thread.join(10)
