"""`hooks/remind-delegate.sh` is advisory: it reminds, and never hands the permission system a
decision (an "allow" would auto-approve the git mutation it exists to discourage; "defer" stops a
`claude -p` run). Each test drives the real hook as the harness would, through one of its two
emit sites, and asserts a reminder is present and no decision field is.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_PLUGIN = REPO_ROOT / "plugins" / "odoo-ai-agents"

REMIND_DELEGATE_HOOK = AGENTS_PLUGIN / "hooks" / "remind-delegate.sh"


def test_remind_delegate_never_allows_risky_git_mutation():
    """remind-delegate.sh must NOT emit permissionDecision:"allow" for a git-mutating Bash
    command dispatched from a role=leaf subagent (the RISKY branch, ~line 66-84).

    Business rule: this hook is documented as ADVISORY-ONLY (HARD CONTRACT header) - it may
    attach `additionalContext` as a reminder, but it must never itself decide the tool call,
    because "allow" bypasses normal permission-rule evaluation (including the user's own
    deny/ask rules) for the exact git mutation the delegation boundary (this file, boundary A/B)
    exists to stop. An advisory hook that auto-approves what it exists to discourage is a
    machine-level bypass of the repo's own git-delegation contract.

    The reminder carries NO permissionDecision at all: every value decides something. "allow"
    skips the user's own rules, "ask"/"deny" impose a prompt or a refusal, and "defer" stops a
    `claude -p` / SDK run at that tool call (Claude Code honors it only non-interactively, as a
    pause for the calling process). Asserting the key is absent - not merely `!= "allow"` - is
    what catches any of those coming back.
    """
    assert REMIND_DELEGATE_HOOK.exists(), f"hook script not found: {REMIND_DELEGATE_HOOK}"

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -am 'do the thing'"},
        # role=leaf per generator/skill_tool_deps.json "agents"."odoo-frontend-coder".role
        "agent_id": "agent-under-test",
        "agent_type": "odoo-frontend-coder",
        "cwd": str(REPO_ROOT),
    }

    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(AGENTS_PLUGIN)

    result = subprocess.run(
        ["bash", str(REMIND_DELEGATE_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, (
        f"remind-delegate.sh must never hard-fail (exit 0 always); "
        f"got rc={result.returncode}, stderr={result.stderr!r}"
    )
    assert result.stdout.strip(), (
        "remind-delegate.sh produced no output for a RISKY git-mutating Bash command from a "
        "role=leaf subagent - expected a hookSpecificOutput reminder JSON on stdout"
    )
    output = json.loads(result.stdout)
    hso = output.get("hookSpecificOutput", {})
    assert hso.get("additionalContext"), f"the reminder text is missing: {output!r}"
    assert "permissionDecision" not in hso and "decision" not in output, (
        f"remind-delegate.sh made a permission decision for a git-mutating Bash command from a "
        f"role=leaf subagent - an ADVISORY hook must leave the call to normal permission "
        f"evaluation (no decision field at all; 'defer' stops a -p/SDK run). Output: {output!r}"
    )


def test_remind_delegate_never_allows_mid_run_delegate_nudge(tmp_path):
    """remind-delegate.sh must NOT emit permissionDecision:"allow" for the OTHER PreToolUse emit
    site - the main-agent mid-run drive-to-done delegate nudge (~line 119), independent of the
    leaf/spawner RISKY-git-mutation site (~line 84) covered by the test above.

    Business rule: same advisory-only contract as the sibling test, exercised via the OTHER
    branch of the same file - no agent_id/agent_type (this is the MAIN agent, not a subagent),
    a heavy/mutating tool (Write/Edit/MultiEdit/Bash), and an active drive-to-done run (a
    `run-*.json` with `status: "NEEDS_NEXT"`) seeded under the resolved ISOLATE dir. This branch
    has its own independent self-gates (active-run glob, not the leaf-role SSOT lookup the other
    branch uses), so a regression that fixed only the RISKY branch and left this one at
    `"allow"` would NOT be caught by `test_remind_delegate_never_allows_risky_git_mutation`
    above - that test never populates agent_id/agent_type, so it can never reach this code path.

    Same contract as the sibling test - no permission decision at all - exercised through a
    structurally independent code path (no leaf-role resolution involved at all).
    """
    assert REMIND_DELEGATE_HOOK.exists(), f"hook script not found: {REMIND_DELEGATE_HOOK}"

    # Seed an active run (status NEEDS_NEXT) under an explicit ISOLATE override so this test
    # never touches the real state root and never depends on git/marker resolution.
    isolate_dir = tmp_path / "isolate"
    isolate_dir.mkdir(parents=True, exist_ok=True)
    (isolate_dir / "run-test123.json").write_text(
        json.dumps({"status": "NEEDS_NEXT"}), encoding="utf-8"
    )

    # The nudge is for a run THIS session drives (hooks/run-ownership.sh): its transcript shows the
    # call that wrote the run record.
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join([
        json.dumps({"type": "assistant", "timestamp": now, "message": {"role": "assistant",
                    "content": [{"type": "tool_use", "id": "toolu_run", "name": "Read",
                                 "input": {"file_path": str(isolate_dir / "run-test123.json")}}]}}),
        json.dumps({"type": "user", "timestamp": now, "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "toolu_run", "content": "{}"}]}}),
    ]) + "\n", encoding="utf-8")

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/whatever.py"},
        # No agent_id/agent_type: this is the MAIN agent (not a subagent) - the branch the
        # test_remind_delegate_never_allows_risky_git_mutation test above cannot reach.
        "cwd": str(REPO_ROOT),
        "transcript_path": str(transcript),
    }

    env = dict(os.environ)
    env["CLAUDE_PLUGIN_ROOT"] = str(AGENTS_PLUGIN)
    env["ODOO_AI_WORKTREE_DIR"] = str(isolate_dir)

    result = subprocess.run(
        ["bash", str(REMIND_DELEGATE_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, (
        f"remind-delegate.sh must never hard-fail (exit 0 always); "
        f"got rc={result.returncode}, stderr={result.stderr!r}"
    )
    assert result.stdout.strip(), (
        "remind-delegate.sh produced no output for a mid-run Write from the main agent with an "
        "active NEEDS_NEXT run - expected a hookSpecificOutput reminder JSON on stdout"
    )
    output = json.loads(result.stdout)
    hso = output.get("hookSpecificOutput", {})
    assert hso.get("additionalContext"), f"the reminder text is missing: {output!r}"
    assert "permissionDecision" not in hso and "decision" not in output, (
        f"remind-delegate.sh made a permission decision for a mid-run Write from the main "
        f"agent - an ADVISORY hook must leave the call to normal permission evaluation (no "
        f"decision field at all; 'defer' stops a -p/SDK run). Output: {output!r}"
    )
