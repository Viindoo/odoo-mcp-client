#!/usr/bin/env bash
# block-coordinator-code-write.sh - PreToolUse HARD DENY. The mechanism behind the "a spawner does
# not author what it dispatches" half of
# ${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md R0.
#
# WHAT IT REFUSES: an agent whose DECLARED ROLE is `coordinator` or `spawner` writing production
# source. Those roles exist to route work to a specialist; the artifact belongs to the teammate the
# role dispatches. The observed breach this exists to stop: a coordinator's teammate dispatch was
# refused, the refusal steered it to "do the work inline", and it edited a module's `__manifest__.py`
# itself - silently degrading a specialist pipeline into one generalist writing code. Prose had
# already failed (the prohibition lived only in frontmatter, which never reaches the agent), so this
# is the mechanism.
#
# DENY iff ALL THREE hold:
#   (a) the CALLER is a subagent - ANY of agent_id / agentId / agent_type / agentType populated.
#       Same identity signal, same V-52 rule, as hooks/remind-delegate.sh. The ROOT is never
#       denied.
#   (b) `agents.<bare agent_type>.role` in the agent-role SSOT (generator/skill_tool_deps.json)
#       resolves to `coordinator` or `spawner`. Data-driven: adding a coordinator to the SSOT arms
#       this gate for it with no edit here, and a `role: leaf` writer (odoo-backend-coder,
#       odoo-frontend-coder, odoo-test-writer, odoo-translator...) is NEVER touched. Both agent_type
#       spellings resolve - bare (`odoo-coder`) and plugin-qualified (`odoo-ai-agents:odoo-coder`) -
#       via the same `${AGENT_TYPE##*:}` normalization remind-delegate.sh uses.
#   (c) the call writes PRODUCTION SOURCE, resolved by extension and location (never a name list):
#       a path ending in one of SOURCE_EXT_RE and NOT under an exempt scratch/state tree
#       (EXEMPT_PATH_RE - the run state root, /tmp, .git, node_modules, __pycache__, .venv).
#       `.claude/` is deliberately NOT exempt: `.claude/worktrees/<branch>/` is where this
#       repo's own flow authors real module source, so exempting it would hole the gate. A worklog,
#       findings file, plan, design doc or any other .md/.json/.yaml artifact is NOT source and
#       passes for every role.
#
# COVERS BASH, NOT ONLY THE EDIT TOOLS - this is the load-bearing half. A gate matching only
# Edit|Write|MultiEdit|NotebookEdit is trivially bypassed here, because this environment's own
# standing guidance tells dispatched agents to PREFER Bash (`sed -i`, heredoc redirect, `tee`,
# `python -c`) over the edit tools. Bash calls flow through the same PreToolUse pipe with the full
# command text visible, so the shell path is inspected too. A guard that omitted it would look
# enforcing while the breach walked straight past it.
#
# WHAT THE BASH INSPECTION CATCHES - seven detectors, each requiring the source path to sit in an
# unambiguous WRITE POSITION (a bare mention of a .py file in a `grep` is not a write):
#   W1 redirect      `> path` / `>> path`                       (`2>&1`, `>&2` excluded)
#   W2 tee           `tee [opts] path`
#   W3 in-place      `sed`/`perl`/`ruby` carrying `-i` (bundled `-pi` and `--in-place` too),
#                    plus a source path in the same command
#   W4 dd            `dd ... of=path`
#   W5 copy/move     `cp|mv|install|rsync ... path` where path is the LAST token of the command
#   W6 patch apply   `git apply`, or `patch` with `-p<N>`/`-i`/`<` - the target paths live inside
#                    the patch, not on the command line, so the verb alone is the signal
#   W7 interpreter   `python|python3|node|ruby|perl` whose command text carries BOTH a source path
#                    AND a file-writing token (`open(`, `write_text`, `writeFileSync`, `writeFile`)
#
# WHAT IT PROVABLY DOES NOT CATCH - stated, not papered over. A gate that claimed completeness it
# lacks would be worse than one that names its limit:
#   - a write whose target path is COMPUTED at runtime (`$F`, `"${dir}/models.py"`, a glob, a
#     variable assigned earlier, a path read from a file): the hook sees no literal source path;
#   - a write performed by a script the command only INVOKES (`bash build.sh`, `make`, `./gen.py`),
#     or by an interpreter whose target path is built inside its own body rather than spelled in
#     the command text (W7 is a best-effort literal match, not an interpreter);
#   - content arriving through an archive or encoder (`tar -x`, `unzip`, `base64 -d >` with a
#     computed name), or through an editor/pager invocation;
#   - a write via an MCP tool, or any tool outside this hook's matcher;
#   - a path spelled through a symlink or an unresolved relative segment that this hook does not
#     normalize (it matches the literal text, it does not resolve the filesystem).
#   The residual is therefore real. It is bounded by the fact that the gate's whole subject set is
#   agents this plugin DECLARES as coordinator/spawner, whose own bodies now also carry the
#   prohibition in prose (the belt this buckle backs up), and by the SubagentStop grounding and
#   teardown gates that judge the turn afterwards. Widen the detectors when a real bypass is
#   OBSERVED; do not widen them on speculation, because every widening is an outage risk on a
#   legitimate command.
#
# FAILS OPEN ON EVERY UNCERTAINTY (the _pass convention this plugin's hooks share): no jq, empty or
# unparseable stdin, a tool outside the matcher, an unresolvable agent_type, a missing or unreadable
# SSOT, a role that is not coordinator/spawner, or a path this hook cannot classify -> silent pass,
# exit 0. Unlike the spawn hook, an unresolved role here PASSES rather than denying: this gate
# refuses on a POSITIVE role claim only, so an agent this plugin knows nothing about is never
# blocked from doing its own work.
#
# SCHEMA: PreToolUse's documented shape - hookSpecificOutput.permissionDecision = "deny" with a
# permissionDecisionReason. Exit code is ALWAYS 0; a PreToolUse hook that hard-fails is an outage.
#
# The reason names no leaf agent by name on purpose: which teammate owns which file class is
# declared by the coordinator's OWN definition, not here, and a hardcoded name list in a hook is
# exactly the drift this repo keeps paying for. The reason points the caller back at its definition
# and at NEEDS_NEXT.

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass
printf '%s' "$INPUT" | jq -e . >/dev/null 2>&1 || _pass

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
case "$TOOL" in
  Edit|Write|MultiEdit|NotebookEdit|Bash) ;;
  *) _pass ;;
esac

# (a) caller must be a subagent - the root is never denied.
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
[[ -n "$AGENT_ID" || -n "$AGENT_TYPE" ]] || _pass
[[ -n "$AGENT_TYPE" ]] || _pass          # no name -> no role -> nothing to assert

# (b) role must POSITIVELY resolve to coordinator/spawner in the SSOT.
DEPS_FILE="${CLAUDE_PLUGIN_ROOT:-}/generator/skill_tool_deps.json"
AGENT_NAME="${AGENT_TYPE##*:}"
[[ -n "$AGENT_NAME" && -f "$DEPS_FILE" ]] || _pass
ROLE="$(jq -r --arg n "$AGENT_NAME" '.agents[$n].role // empty' "$DEPS_FILE" 2>/dev/null || true)"
case "$ROLE" in
  coordinator|spawner) ;;
  *) _pass ;;
esac

# (c) does this call write production source?
# Extension set: the file classes an Odoo module ships as executable/declarative source. Prose and
# machine-readable artifacts (.md/.json/.yaml/.txt/.log/.po) are deliberately absent - a
# coordinator legitimately writes a worklog, a plan and a findings file.
SOURCE_EXT='(py|pyi|ipynb|xml|js|mjs|cjs|ts|tsx|jsx|css|scss|sass|less|csv|sql|xsl|xslt|qweb)'
# Scratch/state trees where even a source-extension file is not module source.
EXEMPT_PATH_RE='(^|/)(\.git|node_modules|__pycache__|\.odoo-ai)(/|$)|^/tmp/|/\.venv/'

_is_source_path() {
  local p="$1"
  [[ -n "$p" ]] || return 1
  printf '%s' "$p" | grep -qiE "\.${SOURCE_EXT}\$" || return 1
  printf '%s' "$p" | grep -qE "$EXEMPT_PATH_RE" && return 1
  return 0
}

TARGET=""
if [[ "$TOOL" != "Bash" ]]; then
  # Edit / Write / MultiEdit all carry file_path; NotebookEdit carries notebook_path.
  P="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // .tool_input.notebook_path // empty' 2>/dev/null || true)"
  _is_source_path "$P" && TARGET="$P"
else
  CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
  [[ -n "$CMD" ]] || _pass
  # One simple command per line, so an end-of-command anchor is meaningful and a detector cannot
  # borrow a path from the next command in a pipeline.
  SEGS="$(printf '%s' "$CMD" | sed -E 's/(\|\||&&|[;|&])/\n/g')"
  PATHTOK="[^[:space:]'\"\`;|&<>]*\.${SOURCE_EXT}"
  while IFS= read -r seg; do
    [[ -n "$seg" ]] || continue
    HIT=""
    # W1 redirect to a source path (a leading digit or & means a stream redirect, not a file).
    printf '%s' "$seg" | grep -qE "(^|[^0-9&>])>>?[[:space:]]*['\"]?${PATHTOK}" && HIT=w1
    # W2 tee
    [[ -z "$HIT" ]] && printf '%s' "$seg" | grep -qE "\btee\b([[:space:]]+-[[:alnum:]-]+)*[[:space:]]+['\"]?${PATHTOK}" && HIT=w2
    # W3 in-place stream edit
    # `-i` is also spelled inside a bundle (`perl -pi -e`) and as `--in-place`; a literal `-i`
    # test misses the bundled form, which is the shape a real in-place rewrite usually takes.
    [[ -z "$HIT" ]] && printf '%s' "$seg" | grep -qE "\b(sed|perl|ruby)\b.*([[:space:]]-[a-zA-Z]*i|[[:space:]]--in-place)" \
      && printf '%s' "$seg" | grep -qE "${PATHTOK}" && HIT=w3
    # W4 dd of=
    [[ -z "$HIT" ]] && printf '%s' "$seg" | grep -qE "\bdd\b.*\bof=['\"]?${PATHTOK}" && HIT=w4
    # W5 copy/move - the destination is the LAST token of the command
    [[ -z "$HIT" ]] && printf '%s' "$seg" | grep -qE "\b(cp|mv|install|rsync)\b.*[[:space:]]['\"]?${PATHTOK}['\"]?[[:space:]]*\$" && HIT=w5
    # W6 patch application - target paths live inside the patch, so the verb is the signal
    [[ -z "$HIT" ]] && printf '%s' "$seg" | grep -qE "\bgit[[:space:]]+apply\b|\bpatch\b([[:space:]]+-(p[0-9]|i)\b|[[:space:]]*<)" && HIT=w6
    # W7 interpreter writing a literal source path (best-effort - see the header's residual list)
    [[ -z "$HIT" ]] && printf '%s' "$seg" | grep -qE "\b(python3?|node|ruby|perl)\b" \
      && printf '%s' "$seg" | grep -qE "open\(|write_text|writeFileSync|writeFile|>" \
      && printf '%s' "$seg" | grep -qE "${PATHTOK}" && HIT=w7
    [[ -n "$HIT" ]] || continue
    if [[ "$HIT" == w6 ]]; then
      TARGET="(patch application: $(printf '%s' "$seg" | cut -c1-80))"
      break
    fi
    CAND="$(printf '%s' "$seg" | grep -oiE "${PATHTOK}" | while IFS= read -r c; do
              _is_source_path "$c" && printf '%s\n' "$c"; done | head -1)"
    if [[ -n "$CAND" ]]; then TARGET="$CAND"; break; fi
  done <<< "$SEGS"
fi

[[ -n "$TARGET" ]] || _pass

REASON="REFUSED: you are \`$AGENT_NAME\`, declared role=$ROLE in this plugin's agent-role SSOT (generator/skill_tool_deps.json). A $ROLE routes work to a specialist and NEVER authors the production source it dispatches - here, $TARGET.

DO THIS INSTEAD: dispatch the teammate your own definition assigns this file class to. If that dispatch is refused or unavailable, END YOUR TURN with status NEEDS_NEXT naming that teammate and the full brief it needs, or with status BLOCKED if you cannot even name it. A refused or missing dispatch is a routing failure to report upward - it never reassigns the authoring to you (snippets/spawner-completion-contract.md R0).

Artifacts that are NOT production source - your worklog, findings, plan or design notes - are unaffected by this gate."

jq -cn --arg reason "$REASON" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$reason}}'
exit 0
