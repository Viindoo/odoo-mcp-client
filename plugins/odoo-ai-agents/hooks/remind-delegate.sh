#!/usr/bin/env bash
# remind-delegate.sh - PreToolUse ADVISORY nudges. Two independent advisories share this file
# (same event, same base subagent-detection, same HARD CONTRACT below):
#
#   (1) Drive-to-done delegate nudge (MAIN agent only, mid-run, Write/Edit/MultiEdit/Bash) -
#       WHY: during an active run the main agent should stay an orchestrator - delegate heavy
#       work to subagents so its context does not grow with run length. This hook NUDGES
#       that, it never enforces it.
#   (2) Git advisory nudge (V-01 mechanism) - a subagent whose best-effort agent_type resolves to
#       a `role: leaf` or `role: node-owner` entry in the agent-role SSOT (generator/skill_tool_deps.json
#       "agents".<name>.role) gets reminded, on a Bash command that runs ANY git (a read, a mutation,
#       `git -C <dir> ...`, inside `bash -c` or `$(...)` alike), that it runs no git itself: a repo
#       fact comes from the odoo-local repo_facts tool, everything else is a request to
#       git-toolkit:git-ops. A HARD LEAF is also reminded on the Agent tool and on Skill(...git-ops...)
#       (it never spawns an agent and never invokes git-ops); a node-owner may do both, so neither
#       is nudged for it. The deterministic guarantee is the `check_orchestration.py` agent-role
#       lint (build-time); THIS is only a same-turn reminder, not the enforcement.
#
# HARD CONTRACT: this hook NEVER decides the tool call - it is advisory only, not enforcement.
#   The main agent (and any subagent) is a decision-maker; hard-blocking is dangerous (can trap
#   the agent / deadlock) - but silently auto-approving is equally dangerous: it would bypass
#   normal permission-rule evaluation (incl. the user's own deny/ask rules) for the exact git
#   mutation / risky tool call this hook exists to discourage. So:
#   - The output carries `additionalContext` ONLY - NO permissionDecision at all. Without one the
#     call goes through normal permission evaluation untouched, so the user still sees any
#     prompt/deny they would otherwise see. No decision value is neutral: "allow"/"ask"/"deny"
#     decide the call, and "defer" is not a no-op either - in a `claude -p` / SDK run it stops the
#     session at that tool call (stop_reason tool_deferred) for the calling process to resume.
#   - Self-gates: (1) requires an active run OF THIS SESSION (an ISOLATE run-*.json with status
#     NEEDS_NEXT, resolved per ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md, that this
#     session wrote last - hooks/run-ownership.sh) -> silent pass otherwise. (2) requires a
#     resolvable role=leaf or role=node-owner match -> silent pass otherwise (no agent-role SSOT,
#     no jq, unresolved agent_type = stay silent, never guess).
#   - (1) is best-effort MAIN-agent-only (skip when we can tell we are in a subagent - V-52:
#     ANY populated agent_id/agent_type means "in a subagent", no `!= general-purpose`
#     special-case, honoring this hook's own "stay silent when unsure" contract). (2) is the
#     mirror: it fires ONLY when we can tell we ARE in a subagent.
#   - Degrades to exit 0 on any uncertainty (no jq, parse error, no run file, no SSOT file).
#   - Said ONCE per context window: each advisory text is emitted only when it is not already in
#     the calling agent's transcript since the last compaction (hooks/advice-once.sh) - the main
#     agent's session transcript for (1), the subagent's own transcript for (2). A repeat on every
#     later Bash/Edit/Write call of the run would tell the agent nothing new and stay in its
#     context each time. An unreadable transcript or helper -> emit (the advisory is never lost).

set -uo pipefail
_pass() { exit 0; }

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

# Shared helpers, resolved relative to THIS script: hooks/advice-once.sh (is this advisory already
# in the context) and hooks/lease-correlation.sh (_lease_agent_transcript - which transcript is a
# subagent's own). Unreadable -> every advisory counts as unseen.
_HOOK_DIR="${BASH_SOURCE[0]%/*}"
_seen() { return 1; }
# hooks/command-segments.sh (_logical_segments) is the SSOT for splitting a command into its simple
# commands; without it the git detector falls back to a plain word match (see _runs_git).
_HAVE_SEGMENTS=false
if [[ -r "$_HOOK_DIR/command-segments.sh" ]]; then
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/command-segments.sh" && _HAVE_SEGMENTS=true
fi
if [[ -r "$_HOOK_DIR/advice-once.sh" && -r "$_HOOK_DIR/lease-correlation.sh" ]]; then
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/advice-once.sh"
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/lease-correlation.sh"
  _seen() { _advice_seen "$1" "$2"; }
fi

# --- does a Bash command RUN git? -------------------------------------------------------------
# Git counts only as a COMMAND WORD - the first word of a simple command, after any `VAR=x`
# assignments and wrappers (`env`, `sudo`, `xargs`, `time`, `command`, `find -exec`, ...) - never as
# an argument of another command (`echo "now git commit it"`, `grep -rn "git status" docs/`,
# `ls ~/git`), a comment (`make test # git hooks`) or a heredoc body. It is followed by a subcommand
# or a global option, so a bare `git` or `command -v git` is no git run. Command positions are the
# start, after `;` `&&` `||` `|` `&` (command-segments.sh), `$(`, a backtick and the string given to
# `sh -c` / `bash -c` / `eval` (each rescanned as a command). The word may be quoted ("git" status)
# or an absolute path (/usr/bin/git). An argv-list or call form is matched anywhere, even inside an
# interpreter's quoted program: ['git','status'], "git", "status", os.system("git status").
# Residual: a command built at run time, or run by a program this scan does not know takes a command
# as its argument, is not seen. This only decides whether to REMIND; it never blocks.
_GITCMD_AWK=$(cat <<'AWK'
function isw(c) { return c == " " || c == "\t" }
function unq(w) { gsub(/'/, "", w); gsub(/"/, "", w); gsub(/\\/, "", w); return w }
function outer(w,   q) {
  q = substr(w, 1, 1)
  if (q == "'" || q == "\"") {
    w = substr(w, 2)
    if (substr(w, length(w), 1) == q) w = substr(w, 1, length(w) - 1)
  }
  return w
}
function wordend(s, i, n,   j, c) {
  j = i
  while (j <= n) {
    c = substr(s, j, 1)
    if (c == "\\") { j += 2; continue }
    if (c == "'") { j++; while (j <= n && substr(s, j, 1) != "'") j++; j++; continue }
    if (c == "\"") {
      j++
      while (j <= n && substr(s, j, 1) != "\"") { if (substr(s, j, 1) == "\\") j++; j++ }
      j++; continue
    }
    if (isw(c) || c == "<" || c == ">" || c == "`" || c == ")") break
    if (c == "$" && substr(s, j + 1, 1) == "(") break
    j++
  }
  return j
}
function followed(s, i, n,   j) {
  j = i
  if (!isw(substr(s, j, 1))) return 0
  while (j <= n && isw(substr(s, j, 1))) j++
  return substr(s, j, 1) ~ /[A-Za-z'"-]/
}
{
  s = $0; n = length(s); i = 1
  cmdpos = 1; wrapopts = 0; shellargs = 0; takec = 0; evalnext = 0; redir = 0
  while (i <= n) {
    c = substr(s, i, 1)
    if (isw(c)) { i++; continue }
    if (c == "#") break
    if (c == "`") { print "N:" substr(s, i + 1); i++; continue }
    if (c == "$" && substr(s, i + 1, 1) == "(") { print "N:" substr(s, i + 2); i += 2; continue }
    if (c == "(" || c == "{" && isw(substr(s, i + 1, 1))) { i++; continue }
    if (c == ")") { i++; continue }
    if (c == "<" || c == ">") {
      i++
      while (i <= n && substr(s, i, 1) ~ /[<>&|]/) i++
      redir = 1; continue
    }
    e = wordend(s, i, n)
    if (e == i) { i++; continue }
    w = substr(s, i, e - i); i = e
    if (substr(w, 1, 1) != "'") {
      p = index(w, "$("); if (p) print "N:" substr(w, p + 2)
      p = index(w, "`"); if (p) print "N:" substr(w, p + 1)
    }
    if (redir) { redir = 0; continue }
    if (takec) { takec = 0; print "N:" outer(w); cmdpos = 0; continue }
    bare = unq(w)
    if (cmdpos) {
      if (evalnext) {
        evalnext = 0
        if (substr(w, 1, 1) ~ /["']/) { print "N:" outer(w); cmdpos = 0; continue }
      }
      if (wrapopts && (bare ~ /^-/ || bare ~ /^[0-9]+$/)) continue
      if (bare ~ /^([^ ]*\/)?git$/) {
        if (followed(s, i, n)) { print "G"; exit }
        cmdpos = 0; continue
      }
      if (bare ~ /^([^ ]*\/)?(env|sudo|doas|xargs|time|nohup|nice|exec|command|builtin|timeout|stdbuf|setsid|ionice|eval|then|do|else|elif|if|while|until)$/ || bare == "!") {
        wrapopts = 1
        if (bare ~ /(^|\/)eval$/) evalnext = 1
        continue
      }
      if (bare ~ /^[A-Za-z_][A-Za-z0-9_]*=/) continue
      if (bare ~ /^([^ ]*\/)?(bash|sh|zsh|dash|ksh|ash)$/) shellargs = 1
      cmdpos = 0; wrapopts = 0; continue
    }
    if (shellargs && bare ~ /^-[A-Za-z]*c[A-Za-z]*$/) { takec = 1; continue }
    if (bare ~ /^-(exec|execdir|ok|okdir)$/) { cmdpos = 1; wrapopts = 0; continue }
  }
}
AWK
)

# _runs_git <command> [depth]: 0 when the command runs git. Strings the awk hands back ("N:...": a
# substitution, a `sh -c` program) are rescanned as commands of their own, a few levels deep.
_runs_git() {
  local cmd="$1" depth="${2:-0}" out line
  # argv-list and call forms: matched anywhere in the text, quoted program included.
  printf '%s' "$cmd" | grep -qE "\\[[[:space:]]*['\"]git['\"][[:space:]]*,|['\"]git['\"][[:space:]]*,[[:space:]]*['\"][-[:alpha:]]|\\([[:space:]]*['\"]git[[:space:]]+[-[:alpha:]]" && return 0
  if [[ "$_HAVE_SEGMENTS" != true ]]; then
    printf '%s' "$cmd" | grep -qE '(^|[^[:alnum:]_.-])git[[:space:]]+[[:alpha:]-]'
    return
  fi
  (( depth <= 4 )) || return 1
  out="$(printf '%s' "$cmd" | _logical_segments | awk "$_GITCMD_AWK" 2>/dev/null)" || return 1
  while IFS= read -r line; do
    case "$line" in
      G) return 0 ;;
      N:*) _runs_git "${line#N:}" $((depth + 1)) && return 0 ;;
    esac
  done <<<"$out"
  return 1
}

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"

# Best-effort subagent detection, shared by both advisories below (V-52 fix: ANY populated
# agent_id/agent_type means "in a subagent" - dropped the old `!= general-purpose` carve-out).
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
IN_SUBAGENT=false
[[ -n "$AGENT_ID" || -n "$AGENT_TYPE" ]] && IN_SUBAGENT=true

# --- (2) Git advisory (V-01) ----------------------------------------------------------------
# Independent of the drive-to-done gates below (no active-run requirement - a leaf or node owner can
# drift any time). Only when we ARE in a subagent AND its best-effort agent_type resolves to a
# `role: leaf` or `role: node-owner` entry in the agent-role SSOT.
if [[ "$IN_SUBAGENT" == true && -n "$AGENT_TYPE" ]]; then
  DEPS_FILE="${CLAUDE_PLUGIN_ROOT:-}/generator/skill_tool_deps.json"
  # Normalize a plugin-qualified type ("odoo-ai-agents:odoo-frontend-coder") to the bare name -
  # the SSOT keys agents by bare name.
  AGENT_NAME="${AGENT_TYPE##*:}"
  ROLE=""
  if [[ -n "$AGENT_NAME" && -f "$DEPS_FILE" ]]; then
    ROLE="$(jq -r --arg n "$AGENT_NAME" '.agents[$n].role // empty' "$DEPS_FILE" 2>/dev/null || true)"
  fi
  if [[ "$ROLE" == "leaf" || "$ROLE" == "node-owner" ]]; then
    RISKY=false
    case "$TOOL" in
      Agent) [[ "$ROLE" == "leaf" ]] && RISKY=true ;;
      Bash)
        CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
        # ANY git command (a read, a mutation, `git -C <dir> ...`, inside `bash -c` or `$(...)` alike):
        # no verb list - neither a read nor a mutation is the agent's to run, so none needs sorting.
        # What counts as running git is defined at _runs_git above.
        if _runs_git "$CMD"; then
          RISKY=true
        fi
        ;;
      Skill)
        SKILL_ARG="$(printf '%s' "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null || true)"
        [[ "$ROLE" == "leaf" && "$SKILL_ARG" == *git-ops* ]] && RISKY=true
        ;;
    esac
    if [[ "$RISKY" == true ]]; then
      if [[ "$ROLE" == "leaf" ]]; then
        CTX="You are running as \"$AGENT_NAME\", declared role=leaf in the agent-role SSOT (generator/skill_tool_deps.json). A HARD LEAF never launches another agent, never invokes git-ops and never runs git itself - not a mutation, not a read. Take a repo fact from the odoo-local repo_facts tool; for anything else write your files and return their list, and your launcher asks git-ops (see snippets/worker-brief.md, snippets/git-delegation.md). This is only a reminder - proceed if you judge this classification does not actually apply to your current dispatch."
      else
        CTX="You are running as \"$AGENT_NAME\", declared role=node-owner in the agent-role SSOT (generator/skill_tool_deps.json). You run no git yourself - not a mutation, not a read. Take a repo fact from the odoo-local repo_facts tool; for anything else invoke Skill(git-toolkit:git-ops) with the request and the expected result (see snippets/git-delegation.md). This is only a reminder - proceed if you judge this classification does not actually apply to your current dispatch."
      fi
      _seen "$(_lease_agent_transcript "$INPUT")" "$CTX" && _pass
      jq -cn --arg ctx "$CTX" \
        '{hookSpecificOutput:{hookEventName:"PreToolUse", additionalContext:$ctx}}'
      exit 0
    fi
  fi
fi

# --- (1) Drive-to-done delegate nudge (MAIN agent only) -------------------------------------
case "$TOOL" in
  Write|Edit|MultiEdit|Bash) ;;          # only the heavy/mutating tools are worth a nudge
  *) _pass ;;
esac

[[ "$IN_SUBAGENT" == false ]] || _pass    # inside a subagent - it is supposed to do the work; do not nag

# Active-run self-gate: only nudge while THIS session drives a run - a NEEDS_NEXT record in this
# project's state dir that this session wrote last (hooks/run-ownership.sh, which also resolves the
# state dir from the hook's own project cwd and owns its read-only fallback). A record another
# session - live or long dead - left there does not make this session mid-run. When ownership cannot
# be told (no readable transcript, a jq that cannot run the scan) the nudge keeps its older rule:
# any NEEDS_NEXT record. Unreadable shared helper -> pass, the plugin-wide convention.
[[ -r "$_HOOK_DIR/run-ownership.sh" ]] || _pass
# shellcheck source=/dev/null
. "$_HOOK_DIR/run-ownership.sh"
CWD="$(printf '%s' "$INPUT" | jq -r '.cwd // empty' 2>/dev/null || true)"
needs_next=()
while IFS= read -r rf; do [[ -n "$rf" ]] && needs_next+=("$rf"); done \
  < <(_needs_next_runs "$(_run_state_dir "$CWD")")
[[ ${#needs_next[@]} -gt 0 ]] || _pass    # no active run -> not in drive-to-done mode -> silent
TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
owned="$(_session_owned_runs "$TRANSCRIPT" "${needs_next[@]}")"
[[ $? -eq 2 || -n "$owned" ]] || _pass

# One text for every heavy tool, so Bash, Edit and Write share one reminder.
CTX="You are mid-run (active drive-to-done run under the namespaced state root - see snippets/state-root-resolution.md). As the orchestrator, prefer delegating Bash/Edit/Write work to a subagent/specialist so your context stays clean for decisions. This is only a reminder - proceed if you judge it right."
_seen "$TRANSCRIPT" "$CTX" && _pass
jq -cn --arg ctx "$CTX" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", additionalContext:$ctx}}'
exit 0
