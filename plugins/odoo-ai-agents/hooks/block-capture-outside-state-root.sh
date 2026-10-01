#!/usr/bin/env bash
# block-capture-outside-state-root.sh - PreToolUse HARD DENY on a browser capture written outside
# the capture area (<state root>/projects plus the override dirs).
#
# WHAT IT REFUSES: a call to one of this plugin's browser MCP families (chrome-devtools,
# playwright, pagecast, each optionally -headed; this plugin's own
# `mcp__plugin_odoo-ai-agents_<family>__` namespace and the bare `mcp__<family>__` names of the
# opt-in families its setup registers - never another plugin's, never a bare chrome-devtools the
# user registered) whose WRITE destination - filePath / filename / outputDirPath / webmPath /
# requestFilePath / responseFilePath - is relative, or absolute but outside the capture area
# (<state root>/projects plus the $ODOO_AI_PROJECT_DIR / $ODOO_AI_WORKTREE_DIR overrides; never
# the rest of the state root, which holds the lease registry; playwright gets the capture area
# only, as it has one output dir). The refusal names a concrete destination under the session's
# ISOLATE dir, or the family's way out when none resolves. `webmPath` (the input of pagecast's
# convert tools, whose output is written beside it) may also point into pagecast's own recording
# dir. A relative destination resolves against the session's working directory, which is
# usually the user's repository, and the servers accept it because the client's roots include
# that directory: the state-root launch flags only make an absolute capture succeed, they cannot
# stop a relative one. Tools that only READ a path (upload_file, browser_file_upload, heap
# snapshot queries, ...) and calls with no destination are never refused.
#
# DRIFT SAFETY: it denies only when the answering server provably runs with its state-root flag
# (the bundled chrome-devtools, started by scripts/mcp/browser_mcp_launch.py, or an opt-in family
# whose answering Claude registration - local, else project, else user scope - carries the flag
# for this state root). Otherwise the call goes through with an advisory naming `/odoo-ai-agents:odoo-setup browser` - a user who has not re-run setup
# keeps working.
#
# The decision lives in scripts/lib/capture_paths.py (realpath + normcase on both sides, Git-Bash
# drive paths translated on Windows). FAILS OPEN on every uncertainty: no python3, an unreadable
# helper, an unparseable payload, any error. Exit code is ALWAYS 0; the deny is
# hookSpecificOutput.permissionDecision = "deny".

set -uo pipefail

command -v python3 >/dev/null 2>&1 || exit 0
_LIB="${BASH_SOURCE[0]%/*}/../scripts/lib/capture_paths.py"
[[ -r "$_LIB" ]] || exit 0
python3 "$_LIB" hook 2>/dev/null || true
exit 0
