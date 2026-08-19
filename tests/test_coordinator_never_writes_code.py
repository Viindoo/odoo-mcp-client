"""Behavioral guard for hooks/block-coordinator-code-write.sh (PreToolUse hard DENY).

The incident this exists to prevent, observed in a live session: `odoo-coder` (declared
`role: coordinator`) had a teammate dispatch refused, the refusal's live rung told it to "do the
work inline", and it edited a module's `__manifest__.py` itself - silently degrading a specialist
pipeline into one generalist writing code. Nothing in the runtime could stop it: there was no
PreToolUse hook on the write tools at all, and the only prohibition the agent nominally had lived
in its frontmatter `description`, which is the launcher's routing listing and never reaches the
running agent's system prompt.

Business rules protected, NOT the implementation:

  - **DENY iff all three hold**: the caller is a subagent; the agent-role SSOT
    (`generator/skill_tool_deps.json` `.agents.<name>.role`) POSITIVELY resolves it to
    `coordinator` or `spawner`; and the call writes production source.
  - **Data-driven subject set.** Every role is read from the live SSOT here, never hardcoded, so
    adding a coordinator arms the gate for it with no edit in either the hook or this file.
  - **A leaf is NEVER touched.** `odoo-backend-coder`, `odoo-frontend-coder`, `odoo-test-writer`
    and every other `role: leaf` writer must sail through the identical call. This is the
    red-before-green half: a gate that over-applies bricks the coding pipeline outright, which is
    strictly worse than the breach it prevents.
  - **The ROOT is never denied**, and an agent this plugin declares no role for is never denied -
    this gate refuses on a positive role claim only.
  - **Source is resolved by extension and location, never by a name list.** A worklog, findings
    file, plan or design note is not source and passes for every role. `.claude/worktrees/...` is
    NOT exempt: that is where this repo's own flow authors real module source.
  - **Bash-mediated writes are covered.** This environment's own standing guidance tells dispatched
    agents to PREFER `Bash` (`sed -i`, heredoc redirect, `tee`, `python -c`) over the edit tools, so
    a gate matching only `Edit|Write|MultiEdit|NotebookEdit` would look enforcing while the breach
    walked past it. Each detector requires the source path in an unambiguous WRITE position - a
    `grep` that merely mentions a `.py` file is not a write.
  - **Fails OPEN on every uncertainty** and always exits 0.

REMAINING FALSE NEGATIVES - stated here, and mirrored in the hook's own header:
  1. A Bash write whose target path is COMPUTED at runtime (`$F`, `"${d}/models.py"`, a glob) is
     invisible to a literal-text detector. `test_documented_bash_residual_is_really_a_residual`
     pins two such shapes as PASSING, so the hole is a measured, reviewable fact rather than a
     surprise.
  2. A write performed by a script the command only invokes (`bash build.sh`, `make`), or inside an
     interpreter body whose path is not spelled in the command text.
  3. Any write through an MCP tool, or any tool outside the hook's matcher.
  4. These tests prove the hook DECIDES correctly on a payload. They cannot prove the harness
     delivers that payload for every write path in every CLI build - that is what the live
     PreToolUse capture behind this design established once, and what `hooks.json` registration
     (asserted below) keeps wired.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = ROOT / "plugins" / "odoo-ai-agents"
HOOK = PLUGIN_ROOT / "hooks" / "block-coordinator-code-write.sh"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
DEPS_FILE = PLUGIN_ROOT / "generator" / "skill_tool_deps.json"

_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(
    shutil.which("jq") is None or _BASH is None,
    reason="hook needs jq + bash; absent here (the hook itself degrades to a silent pass)",
)


def _by_role() -> dict[str, list[str]]:
    data = json.loads(DEPS_FILE.read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for name, entry in data.get("agents", {}).items():
        out.setdefault(entry.get("role", ""), []).append(name)
    return out


_BY_ROLE = _by_role()
NON_AUTHORS = sorted(_BY_ROLE.get("coordinator", []) + _BY_ROLE.get("spawner", []))
LEAVES = sorted(_BY_ROLE.get("leaf", []))

# A module source path in each of the file classes an Odoo change actually touches.
SOURCE_PATHS = [
    "/w/addons/sale_x/__manifest__.py",
    "/w/addons/sale_x/models/sale_order.py",
    "/w/addons/sale_x/views/sale_views.xml",
    "/w/addons/sale_x/security/ir.model.access.csv",
    "/w/addons/sale_x/static/src/js/widget.js",
    "/w/addons/sale_x/static/src/scss/style.scss",
]
# Artifacts a coordinator legitimately writes.
NON_SOURCE_PATHS = [
    "/w/.odoo-ai/worklogs/run-1/odoo-coder.md",
    "/w/.odoo-ai/findings/gap.json",
    "/w/designs/tdd-sale-x.md",
    "/w/plan.yaml",
    "/w/.odoo-ai/scratch/one_off.py",
]


def _run(tool, tool_input, *, agent_type="odoo-coder", agent_id="a1", env_overrides=None, raw=None):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    if agent_id is not None:
        payload["agent_id"] = agent_id
    if agent_type is not None:
        payload["agent_type"] = agent_type
    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(PLUGIN_ROOT)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [_BASH, str(HOOK)],
        input=raw if raw is not None else json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def _denied(proc):
    assert proc.returncode == 0, f"must exit 0; rc={proc.returncode} stderr={proc.stderr!r}"
    assert proc.stdout.strip(), "expected a deny JSON on stdout, got nothing"
    out = json.loads(proc.stdout)
    hso = out.get("hookSpecificOutput", {})
    assert hso.get("hookEventName") == "PreToolUse"
    assert hso.get("permissionDecision") == "deny", f"expected deny, got {out!r}"
    assert "decision" not in out, (
        "the SubagentStop `{'decision':'block'}` shape is a different event's schema and is "
        f"silently ignored on PreToolUse: {out!r}"
    )
    reason = hso.get("permissionDecisionReason") or ""
    assert reason.strip(), "a deny with no reason strands the caller"
    return reason


def _passed(proc):
    assert proc.returncode == 0, f"must exit 0; rc={proc.returncode} stderr={proc.stderr!r}"
    assert proc.stdout.strip() == "", f"expected a SILENT pass, got {proc.stdout!r}"


# --------------------------------------------------------------------------- #
# subject set sanity - the guard must not be able to pass vacuously
# --------------------------------------------------------------------------- #
def test_the_ssot_declares_both_subject_sets():
    """Both halves below are data-driven. An empty coordinator/spawner set would make every DENY
    case vanish and the file would look green while testing nothing; an empty leaf set would do the
    same to the over-application half."""
    assert NON_AUTHORS, (
        "no agent declares role coordinator|spawner in the SSOT - the deny half would be vacuous"
    )
    assert LEAVES, "no agent declares role leaf in the SSOT - the pass half would be vacuous"


# --------------------------------------------------------------------------- #
# DENY - a non-authoring role writing source
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("agent", NON_AUTHORS)
@pytest.mark.parametrize("path", SOURCE_PATHS)
@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit"])
def test_a_non_authoring_role_cannot_write_module_source_with_an_edit_tool(agent, path, tool):
    """The literal shape of the observed incident: `Edit` on `__manifest__.py` from a coordinator."""
    _denied(_run(tool, {"file_path": path}, agent_type=agent))


@pytest.mark.parametrize("qualified", [False, True])
def test_both_agent_type_spellings_resolve_to_the_same_role(qualified):
    """`agent_type` is a verbatim carry-through of the dispatch-time `subagent_type` string, which
    may be bare or plugin-qualified. The qualified form could not be observed directly (nested
    dispatch is denied), so both must resolve or the gate silently stops applying to the exact
    agent it was built for."""
    agent = NON_AUTHORS[0]
    agent_type = f"odoo-ai-agents:{agent}" if qualified else agent
    _denied(_run("Edit", {"file_path": SOURCE_PATHS[0]}, agent_type=agent_type))


def test_notebook_edit_is_covered_by_its_own_path_key():
    """NotebookEdit carries `notebook_path`, not `file_path`. Reading only `file_path` would leave
    the matcher entry decorative - registered, never able to fire."""
    _denied(_run("NotebookEdit", {"notebook_path": "/w/addons/sale_x/explore.ipynb"}))


def test_the_deny_reason_routes_to_needs_next_and_never_to_writing_it_anyway():
    """A refusal with no move is a refusal the agent works around. It must name the rung
    (NEEDS_NEXT), say a refused dispatch is reported upward, and say plainly which artifacts are
    unaffected - otherwise a coordinator concludes it may not write its own worklog either."""
    reason = _denied(_run("Edit", {"file_path": SOURCE_PATHS[0]}))
    low = reason.lower()
    assert "needs_next" in low, f"the rung must be named: {reason!r}"
    assert "never" in low and "routing failure" in low, (
        f"must state a refused dispatch is reported upward, not absorbed: {reason!r}"
    )
    assert "worklog" in low, (
        f"must say which of its own artifacts are unaffected, or the refusal over-reads: {reason!r}"
    )
    assert SOURCE_PATHS[0] in reason, f"must name the file it refused: {reason!r}"


# --------------------------------------------------------------------------- #
# PASS - the gate must not over-apply
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("agent", LEAVES)
def test_every_leaf_writer_is_untouched(agent):
    """RED-BEFORE-GREEN, and the outage this guard prevents: `odoo-backend-coder` and
    `odoo-frontend-coder` exist to write exactly these files. A gate that denied them would brick
    the coding pipeline - strictly worse than the breach it was built to stop."""
    _passed(_run("Edit", {"file_path": SOURCE_PATHS[1]}, agent_type=agent))
    _passed(_run("Bash", {"command": f"sed -i s/a/b/ {SOURCE_PATHS[1]}"}, agent_type=agent))


@pytest.mark.parametrize("path", NON_SOURCE_PATHS)
def test_a_non_authoring_role_still_writes_its_own_artifacts(path):
    """A coordinator's worklog, findings, plan and design notes are its job. Denying them would
    make the gate unusable and invite an exemption that reopens the real hole."""
    _passed(_run("Write", {"file_path": path}))


def test_the_root_is_never_denied():
    """No agent-identity field means the root conversation, which this plugin's whole
    drive-to-done flow writes from."""
    _passed(_run("Edit", {"file_path": SOURCE_PATHS[0]}, agent_type=None, agent_id=None))


def test_an_agent_with_no_declared_role_is_never_denied():
    """This gate refuses on a POSITIVE role claim only. `general-purpose` is a real, measured
    caller absent from this plugin's SSOT; blocking its writes would break ordinary delegated work
    on the strength of a role this plugin never declared."""
    _passed(_run("Edit", {"file_path": SOURCE_PATHS[0]}, agent_type="general-purpose"))


def test_a_worktree_path_is_not_mistaken_for_a_scratch_tree():
    """`.claude/worktrees/<branch>/` is where this repo's own flow authors real module source.
    Exempting `.claude/` wholesale - an easy, plausible-looking simplification - would punch a hole
    straight through the gate."""
    _denied(_run("Edit", {"file_path": "/repos/x/.claude/worktrees/f/addons/x/models/s.py"}))


# --------------------------------------------------------------------------- #
# Bash-mediated writes - the path this environment actively steers agents into
# --------------------------------------------------------------------------- #
BASH_WRITES = [
    ("redirect", "cat > /w/addons/x/models/sale.py <<'EOF'\nclass A: pass\nEOF"),
    ("append", "echo '<record/>' >> /w/addons/x/views/v.xml"),
    ("tee", "printf '%s' x | tee -a /w/addons/x/security/ir.model.access.csv"),
    ("sed-i", "sed -i 's/a/b/' /w/addons/x/models/sale.py"),
    ("perl-i", "perl -pi -e 's/a/b/' /w/addons/x/models/sale.py"),
    ("dd", "dd if=/tmp/src of=/w/addons/x/models/sale.py"),
    ("cp", "cp /tmp/new.py /w/addons/x/models/sale.py"),
    ("mv", "mv /tmp/new.py /w/addons/x/models/sale.py"),
    ("git-apply", "git apply /tmp/change.patch"),
    ("patch", "patch -p1 < /tmp/change.patch"),
    ("python-open", "python3 -c \"open('/w/addons/x/models/sale.py','w').write('x')\""),
    ("pipeline-tail", "grep -rn foo /w/addons | sed -i 's/a/b/' /w/addons/x/models/sale.py"),
]


@pytest.mark.parametrize("label,command", BASH_WRITES, ids=[c[0] for c in BASH_WRITES])
def test_bash_mediated_source_writes_are_denied(label, command):
    """The load-bearing half. This session's own standing guidance instructs dispatched agents to
    make file changes with `sed`, heredocs or short scripts rather than the edit tools, so for a
    dispatched agent the shell is plausibly the MAIN write path, not an edge case. A gate that
    matched only the edit tools would be a guard that looks enforcing while the breach walks past
    it - this repo's signature failure mode."""
    _denied(_run("Bash", {"command": command}))


BASH_READS = [
    ("grep", "grep -n 'def create' /w/addons/x/models/sale.py"),
    ("grep-to-scratch", "grep -rn foo /w/addons/x/models/sale.py > /tmp/out.txt"),
    ("ls", "ls -l /w/addons/x/models/sale.py"),
    ("cat", "cat /w/addons/x/__manifest__.py"),
    ("sed-read", "sed -n '1,20p' /w/addons/x/models/sale.py"),
    ("sed-stream", "sed -e 's/x/i/' /w/addons/x/models/sale.py | head -5"),
    ("odoo-bin", "odoo-bin -u sale_x --stop-after-init 2>&1 | tail -20"),
    ("allocator", "python3 scripts/lib/allocator.py release tok-1"),
    ("git-status", "git status --porcelain"),
    ("pytest", "python -m pytest tests/test_sale.py -q"),
]


@pytest.mark.parametrize("label,command", BASH_READS, ids=[c[0] for c in BASH_READS])
def test_bash_reads_and_runs_are_never_denied(label, command):
    """Scope discipline, and the other half of red-before-green. A coordinator must still be able
    to read source, run the integrated test, drive the allocator, and redirect output to scratch. A
    detector that fired on any command merely MENTIONING a `.py` path would deny all of these and
    be switched off within a day."""
    _passed(_run("Bash", {"command": command}))


DOCUMENTED_RESIDUAL = [
    ("computed-path", 'F=/w/addons/x/models/sale.py; printf "x" > "$F"'),
    ("invoked-script", "bash /tmp/regenerate_models.sh"),
]


@pytest.mark.parametrize(
    "label,command", DOCUMENTED_RESIDUAL, ids=[c[0] for c in DOCUMENTED_RESIDUAL]
)
def test_documented_bash_residual_is_really_a_residual(label, command):
    """PINS THE HOLE OPEN ON PURPOSE. The hook's header claims it cannot see a write whose target
    is computed at runtime, or one performed inside a script it only invokes. This test asserts
    those shapes PASS, so the documented limit is a measured fact rather than a hopeful sentence -
    and so that anyone who later closes one of them has to come here and say so deliberately
    (a gate that claims completeness it lacks is worse than one that states its limit)."""
    _passed(_run("Bash", {"command": command}))


# --------------------------------------------------------------------------- #
# FAIL-OPEN paths
# --------------------------------------------------------------------------- #
def test_malformed_json_passes_silently():
    _passed(_run("Edit", {}, raw="{not json"))


def test_empty_stdin_passes_silently():
    _passed(_run("Edit", {}, raw=""))


def test_missing_jq_passes_silently(tmp_path):
    empty = tmp_path / "nothing"
    empty.mkdir()
    _passed(_run("Edit", {"file_path": SOURCE_PATHS[0]}, env_overrides={"PATH": str(empty)}))


def test_unreadable_ssot_passes_silently():
    """Unlike the spawn hook, this gate cannot decide anything without the role SSOT - it refuses
    on a positive role claim only. With the SSOT unreachable it must fail OPEN, never guess."""
    _passed(
        _run("Edit", {"file_path": SOURCE_PATHS[0]}, env_overrides={"CLAUDE_PLUGIN_ROOT": ""})
    )


@pytest.mark.parametrize("tool_input", [None, "a string, somehow", {}])
def test_unreadable_tool_input_passes_silently(tool_input):
    _passed(_run("Edit", tool_input))


@pytest.mark.parametrize("tool", ["Read", "Grep", "Glob", "Skill", "Agent", "TodoWrite"])
def test_tools_outside_the_matcher_pass_silently(tool):
    _passed(_run(tool, {"file_path": SOURCE_PATHS[0]}))


# --------------------------------------------------------------------------- #
# hooks.json registration - an unregistered gate is a mechanism never reached
# --------------------------------------------------------------------------- #
def _pretooluse_groups():
    return json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]


def test_hooks_json_registers_the_gate_and_its_matcher_reaches_every_write_tool():
    """The plugin's dominant defect class is a correct mechanism nothing ever calls. The matcher is
    evaluated BEFORE the script runs, so a matcher that misses `Bash` would leave the entire
    shell-write half of this file testing a script the harness never invokes."""
    import re

    groups = [
        g
        for g in _pretooluse_groups()
        if any("block-coordinator-code-write.sh" in h.get("command", "") for h in g.get("hooks", []))
    ]
    assert groups, "hooks.json must register block-coordinator-code-write.sh under PreToolUse"
    for g in groups:
        matcher = g.get("matcher")
        assert matcher, "the gate must be matcher-scoped, not run on every tool call"
        for tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Bash"):
            assert re.match(matcher, tool), (
                f"matcher {matcher!r} must accept {tool!r}, or the gate never runs for it - "
                "omitting Bash in particular would leave the main write path uncovered"
            )
        for tool in ("Read", "Grep", "Agent"):
            assert not re.match(matcher, tool), (
                f"matcher {matcher!r} must not over-match {tool!r}"
            )
