#!/usr/bin/env bash
# enforce-teardown.sh - resource-teardown enforcement for odoo-ai-agents (L1.6).
#
# Registered under BOTH SubagentStop (alongside enforce-grounding.sh) and Stop.
#
# NAMED DESIGN RULE (drives every branch below - a future contributor MUST NOT
# invert it): BLOCK ONLY THE PROVABLE LEDGER LIE (instances); NUDGE THE FUZZY
# TRANSCRIPT COUNT (browsers).
#   - Odoo INSTANCES are detached OS processes (an `odoo-bin` master + workers +
#     its Postgres backend) that OUTLIVE the Claude session and leak RAM until a
#     human notices. Their existence is provable from the allocator LEDGER (ground
#     truth, not the fuzzy transcript). So a live owned lease at a subagent's turn
#     END is a HARD BLOCK (SubagentStop only) with a deterministic release cmd, on
#     ANY terminal status: a completion claim, `NEEDS_NEXT` with no handle forwarded,
#     an out-of-enum status, NO `continuation` status at all, AND a `BLOCKED` /
#     `NEEDS_CONTEXT` stopped-run report. Only two things pass - the lease is GONE
#     from the ledger (released or parked), or a T4 named handoff forwards
#     `INSTANCE_HANDLE`. The gate is STATUS-BLIND on purpose: a dispatch that cannot
#     RELEASE can always still NAME a catcher, so `BLOCKED` is no longer a door the
#     lease escapes through unowned. A lease the caller PARKED is not a
#     live lease at all for this purpose: park already stopped its process group, so it
#     leaks no RAM, and the allocator's verdict reports it as `state: parked`. Its three
#     exits (release / park / forwarded INSTANCE_HANDLE) are the ones the block message
#     names.
#   - WHOSE lease: only the lease TOKENS this subagent itself obtained, read from its OWN
#     transcript (see "Token correlation" below) - never a run id. A run id is shared by
#     the parent and every sibling of one run BY DESIGN, so correlating on it ordered a
#     child to release its parent's and its siblings' live instances.
#   - WHETHER it is live: the allocator's own verdict (`allocator.py list --tokens ...
#     --with-verdict`), never a liveness rule re-derived here.
#   - BROWSER pages die WITH the session's MCP server process - a bounded, self-
#     healing leak. Their count is only inferable from the transcript (open/close
#     calls), which is fuzzy. So browser findings are ADVISORY ONLY (systemMessage,
#     NEVER decision:block) on both SubagentStop and Stop - prevention + a nudge.
#
# CONTRACT (Claude Code Stop / SubagentStop): stdin JSON has transcript_path,
# stop_hook_active, hook_event_name; SubagentStop also carries agent_transcript_path.
#   - WHICH transcript: on SubagentStop `agent_transcript_path` (the subagent's OWN
#     transcript). The payload's `transcript_path` is the WHOLE session's (the parent
#     plus every sibling), so reading it attributed the parent's acquires and browser
#     pages to whichever subagent stopped next. It is read only on Stop, where the
#     session transcript IS the stopping agent's. Same rule, same reason as
#     enforce-background-wait.sh.
#   - Self-gates (clone of enforce-grounding.sh): missing jq / missing transcript
#     / stop_hook_active=true / a non-teardown-shaped subagent -> silent exit 0.
#   - Block form (instances, SubagentStop only): {"decision":"block","reason":...}.
#   - Advisory form (browsers): {"continue":true,"systemMessage":...}.
#   - Degrades to exit 0 on ANY uncertainty (no jq/python3/allocator, parse error,
#     no verdict, no correlated token). This is the ONLY hard-block gate in the system: a false
#     block halts real work, so every branch prefers a FALSE-NEGATIVE over a
#     false-positive - never block on ambiguity.

set -uo pipefail

_pass() { exit 0; }   # approve / stay out of the way

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass   # already continuing from a prior block - no loop

EVENT="$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || true)"

# The subagent's OWN transcript on SubagentStop; the session transcript only on Stop (see
# CONTRACT). A SubagentStop without agent_transcript_path is uncertainty -> pass, never a
# fallback onto the session transcript (that fallback IS the defect).
if [[ "$EVENT" == "SubagentStop" ]]; then
  TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.agent_transcript_path // empty' 2>/dev/null || true)"
else
  TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
fi
[[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]] || _pass

# --- Normalize the subagent's own transcript (ASSISTANT-authored only) -----------------------
# Same posture as enforce-grounding.sh: tool CALLS are counted from real `tool_use`
# blocks and run-id / continuation signals are read only from the assistant's own
# text - never from an injected brief/tool_result that quotes a handle or a command.
# tool_use -> "CALL\t<name>\t<command-or-path>" (newlines in the command field are
# squashed to spaces so each CALL stays exactly one line for grep -c). text -> raw
# (newlines preserved) so the ```continuation block parses line-by-line.
NORM="$(jq -rR 'fromjson? | (.message // .) as $m
  | (($m.role // .type) // "") as $role
  | select($role == "assistant")
  | ($m.content // [])
  | (if type == "array" then .[] else empty end)
  | if (.type == "tool_use") then
        "CALL\t" + ((.name // "")|tostring) + "\t"
          + (((.input.command // .input.file_path // .input.path // "")|tostring) | gsub("\n";" "))
    elif (.type == "text") then
        "TEXT\t" + ((.text // "")|tostring)
    else empty end' "$TRANSCRIPT" 2>/dev/null || true)"

_cnt() { printf '%s\n' "$NORM" | grep -ciE "$1" 2>/dev/null | tr -d '[:space:]' || true; }

# --- Browser matcher (SUFFIX-keyed across ALL prefix namespaces) -----------------------------
# Names look like mcp__chrome-devtools__new_page / mcp__chrome-devtools-headed__new_page /
# mcp__plugin_odoo-ai-agents_chrome-devtools__new_page / playwright + pagecast + -headed +
# plugin_* variants. Key ONLY on the trailing __<name>, never a fixed server prefix, so a new
# namespace is matched for free. Each CALL line is "CALL\t<name>\t<cmd>"; `[^\t]*__<name>\t`
# anchors on the name field ending in __<name>.

# chrome-devtools: ACQUIRE = new_page ONLY; RELEASE = close_page. navigate_page / select_page /
# list_pages NEVER count (matching them would false-block the repo's one-page-reuse discipline).
NEW_PAGE=$(_cnt $'^CALL\t[^\t]*__new_page\t')
CLOSE_PAGE=$(_cnt $'^CALL\t[^\t]*__close_page\t')

# playwright: a page is IMPLICIT and close is close-ALL (one browser_close satisfies any number
# of opens). DRIVE = any browser_* call EXCEPT the lifecycle verbs (close + video/tracing pairs +
# resume + tabs) - a negative list so a new driving verb still counts. Finding = DRIVE>0 with a
# ZERO close signal.
# browser_tabs is credited as a CLOSE signal: `browser_tabs {action: close}` is a legit per-tab
# close, but its `action` is a tool_use input we do not capture in NORM. Rather than false-nudge a
# real per-tab close, we treat ANY browser_tabs call as satisfying close (and exclude it from
# DRIVE). Trade-off: a `browser_tabs {action: new}` that is never closed is not nudged - acceptable
# because browser findings are ADVISORY only (a bounded, session-scoped leak), never a hard block.
PW_ALL=$(_cnt $'^CALL\t[^\t]*__browser_')
PW_LIFECYCLE=$(_cnt $'^CALL\t[^\t]*__browser_(close|tabs|start_video|stop_video|start_tracing|stop_tracing|resume)\t')
PW_DRIVE=$(( PW_ALL - PW_LIFECYCLE ))
PW_CLOSE=$(_cnt $'^CALL\t[^\t]*__browser_close\t')
PW_TABS=$(_cnt $'^CALL\t[^\t]*__browser_tabs\t')
PW_SVIDEO=$(_cnt $'^CALL\t[^\t]*__browser_start_video\t')
PW_EVIDEO=$(_cnt $'^CALL\t[^\t]*__browser_stop_video\t')
PW_STRACE=$(_cnt $'^CALL\t[^\t]*__browser_start_tracing\t')
PW_ETRACE=$(_cnt $'^CALL\t[^\t]*__browser_stop_tracing\t')

# pagecast: record_page without stop_recording. record_and_gif is SELF-CONTAINED (name ends
# __record_and_gif != __record_page) so it is ignored. interact_page / convert_* / list_recordings
# never count.
RECORD=$(_cnt $'^CALL\t[^\t]*__record_page\t')
STOP_REC=$(_cnt $'^CALL\t[^\t]*__stop_recording\t')

BROWSER_ANY=$(( NEW_PAGE + CLOSE_PAGE + PW_ALL + RECORD + STOP_REC ))

# Build the ADVISORY message (concrete unmatched counts). Never blocks.
BROWSER_MSG=""
_add_note() { if [[ -n "$BROWSER_MSG" ]]; then BROWSER_MSG="$BROWSER_MSG; $1"; else BROWSER_MSG="$1"; fi; }
[[ "$NEW_PAGE" -gt "$CLOSE_PAGE" ]] && \
  _add_note "$NEW_PAGE new_page vs $CLOSE_PAGE close_page - close the chrome-devtools pages you created before your terminal status"
[[ "$PW_DRIVE" -gt 0 && "$PW_CLOSE" -eq 0 && "$PW_TABS" -eq 0 ]] && \
  _add_note "playwright: $PW_DRIVE driving call(s) with 0 browser_close - one browser_close closes everything you drove; call it before your terminal status"
[[ "$PW_SVIDEO" -gt "$PW_EVIDEO" ]] && \
  _add_note "$PW_SVIDEO browser_start_video vs $PW_EVIDEO browser_stop_video - stop the video before your terminal status"
[[ "$PW_STRACE" -gt "$PW_ETRACE" ]] && \
  _add_note "$PW_STRACE browser_start_tracing vs $PW_ETRACE browser_stop_tracing - stop tracing before your terminal status"
[[ "$RECORD" -gt "$STOP_REC" ]] && \
  _add_note "$RECORD record_page vs $STOP_REC stop_recording - stop the pagecast recording before your terminal status"

# --- Continuation status + INSTANCE_HANDLE forwarding (assistant text only) -------------------
# Capture the body of the LAST ```continuation fenced block (reuse parse-continuation.sh's fence
# detection), then derive status + handle-forwarding from that body. Keeping it a single captured
# block means an INSTANCE_HANDLE mentioned in prose OUTSIDE the block never counts as a forward.
CONT_BLOCK="$(printf '%s\n' "$NORM" | awk '
  /```[ \t]*continuation/ { incont=1; buf=""; next }
  incont && /```/         { incont=0; last=buf; next }
  incont                  { buf=buf $0 "\n" }
  END { printf "%s", last }' 2>/dev/null || true)"
STATUS="$(printf '%s\n' "$CONT_BLOCK" | awk '
  /status:/ { line=$0; sub(/.*status:[ \t]*/,"",line); sub(/[ \t].*/,"",line); last=line }
  END { print last }' 2>/dev/null || true)"
# Normalize to a comparable KEY before any classification: uppercase, then keep only the leading
# [A-Z_] token. The gate below blocks the COMPLEMENT of a small allowed set, so a cosmetic
# spelling (`status: `BLOCKED``, `status: blocked`, a trailing comma) must never be what turns a
# declared non-completion status into a hard block. Empty KEY = no machine-readable status.
STATUS_KEY="$(printf '%s' "$STATUS" | tr 'a-z' 'A-Z' | sed -E 's/^[^A-Z_]*//; s/[^A-Z_].*$//' 2>/dev/null || true)"
FWD_HANDLE=0
printf '%s' "$CONT_BLOCK" | grep -q 'INSTANCE_HANDLE' 2>/dev/null && FWD_HANDLE=1

# --- Token correlation (ONLY leases THIS subagent itself obtained) ----------------------------
# "Which leases did THIS dispatch obtain?" is answered by hooks/lease-correlation.sh, the ONE
# implementation this gate shares with block-unowned-lease-mutation.sh (read its header for exactly
# which calls count, and why serving or resuming a forwarded token and a time window never do). A
# shared copy is what keeps the two gates from disagreeing: this gate orders a release that the
# mutation gate must then allow. Helper unreadable -> no correlated token -> fail open.
_LEASE_LIB="${BASH_SOURCE[0]%/*}/lease-correlation.sh"
OWN_TOKENS=""
if [[ -r "$_LEASE_LIB" ]]; then
  # shellcheck source=/dev/null
  . "$_LEASE_LIB"
  declare -F _lease_owned_tokens >/dev/null 2>&1 && OWN_TOKENS="$(_lease_owned_tokens "$TRANSCRIPT")"
fi

# Self-gate (clone of enforce-grounding.sh's "non-Odoo subagent" gate): no browser activity AND
# no lease this subagent obtained -> not a teardown-shaped subagent -> stay out of the way. A pure
# CONSUMER of a forwarded INSTANCE_HANDLE lands here: it obtained nothing, whatever it quotes.
if [[ "$BROWSER_ANY" -eq 0 && -z "$OWN_TOKENS" ]]; then
  _pass
fi

# --- Instance check: BLOCKING, SubagentStop only, named handoff excepted ----------------------
# Ground truth is the allocator's own VERDICT (`list --with-verdict`), never the transcript and
# never a liveness rule copied into this file: the verdict is the SSOT for "would anything
# reclaim this lease", and a second copy here is what drifted before (a hard-coded TTL fallback
# that silently disagreed with the allocator the day its default changed). Emits the ONE hard
# block in the system; everything above is advisory.
_alloc_list_json() {
  # One `allocator.py list` call, JSON envelope in, the lease array out ("" on any failure).
  local out
  out="$(timeout 5 python3 "$ALLOC" list --with-verdict --show-tokens --format json "$@" \
         2>/dev/null || true)"
  printf '%s' "$out" | jq -c 'select(.ok == true) | (.fields.leases // [])' 2>/dev/null || true
}

_instance_block_reason() {
  # Requires: SubagentStop event, python3 + allocator.py, a correlated token, no
  # forwarded handle. Prints the block reason on success; prints nothing (rc!=0) to fall through.
  [[ "$EVENT" == "SubagentStop" ]] || return 1
  # The gate is STATUS-BLIND. It asks ONE question - "is a live lease this dispatch obtained
  # still in the ledger, with nobody named to take it?" - and `status` is not part of the answer.
  #
  # It did NOT always work this way. `NEEDS_NEXT` was once an unconditional pass, and so were
  # `BLOCKED` / `NEEDS_CONTEXT`, on the reasoning that T4 makes BLOCKED the sanctioned outcome
  # when teardown ITSELF fails ("report the lease token ... so the caller or allocator GC can reap
  # it"), so blocking it would trap the one path the contract gives that failure. That reasoning
  # confused two different things: being unable to RELEASE, and being unable to NAME A CATCHER.
  # A dispatch can always do the second - forwarding `INSTANCE_HANDLE` is text in its own
  # continuation fence, needs no tool, no permission, and no live process - so requiring it traps
  # nobody. It is the FIRST that can be taken away, and when it is (an allocator error, a refusing
  # process, a HARNESS PERMISSION DENIAL on the give-back verb - see permission-denied-teardown.sh)
  # the old pass-set turned that into a silent, unowned leak: the lease outlived the dispatch with
  # no named owner, and only the allocator's TTL backstop reclaimed it, hours later.
  #
  # So every terminal status now falls through to the same handoff test below: `DONE`,
  # `NEEDS_NEXT`, `BLOCKED`, `NEEDS_CONTEXT`, a value outside the enum, or NO machine-readable
  # `continuation` status at all (that one leaks worst - no status means no fence, so no forwarded
  # handle and no named catcher either, and a SubagentStop IS the end of the dispatch, so nothing
  # runs later to release it). A stopped run still reports honestly - it just names who inherits
  # the lease while it does. When teardown is what failed, the catcher is the DISPATCHING CALLER;
  # the block message below names it, so satisfying this gate never invents a fictional catcher.
  # T4's exception is read from the SAME fence-scoped extraction as the status (never from free
  # prose - a handle promised in prose forwards nothing a consumer can act on).
  [[ "$FWD_HANDLE" == "1" ]] && return 1   # INSTANCE_HANDLE forwarded in next.inputs -> handoff -> pass
  [[ -n "$OWN_TOKENS" ]] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  ALLOC="${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/allocator.py"
  [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "$ALLOC" ]] || return 1

  # Candidate rows: exactly the leases named by the tokens this subagent obtained.
  local cand="[]" part
  part="$(_alloc_list_json --tokens "$(printf '%s\n' "$OWN_TOKENS" | paste -sd, -)")"
  [[ -n "$part" ]] && cand="$part"

  # LIVE, per the allocator's verdict: running or reserved (never parked / orphaned /
  # reclaiming), not a shared render server (cross-session by design, never one consumer's to
  # drop - which is also why the lease a LAUNCHING series-mode instance_serve registers never
  # reaches this list: that path only ever registers a `shared` lease; the correlation still counts
  # it for block-unowned-lease-mutation.sh arm A4, so its launcher may stop it on an explicit user
  # request), and not something the AUTOMATIC reclaim would take anyway (`condemn_auto` set: a dead
  # or recycled server pid, an ended session past its grace) - such a lease leaks nothing a
  # dispatch could still fix. A PARKED lease is skipped on purpose, not as a hole: park already did
  # the RAM half of teardown, and blocking it would refuse the very exit this gate permits. A row
  # with no verdict at all (an allocator too old to give one) is uncertainty -> not blocked.
  local rows
  rows="$(printf '%s' "$cand" | jq -r '
      unique_by(.token) | .[]
      | select((.mode // "") != "shared")
      | select(.verdict != null)
      | select((.verdict.state // "") == "running" or (.verdict.state // "") == "reserved")
      | select(.verdict.condemn_auto == null)
      | [(.token // ""), ((.owner.run_id // .owner.session_id // "") | tostring),
         (.verdict.state // ""), (.verdict.protected_by // "none")]
      | map(if . == "" then "-" else . end) | @tsv' 2>/dev/null || true)"
  [[ -n "$rows" ]] || return 1

  # NOTE on the TSV shape: every field is forced NON-EMPTY ("-" stands for empty). `read` with a
  # whitespace IFS (tab included) silently SQUASHES an empty middle field into its neighbour.
  local lines n token rid state prot rid_arg mcp_rid
  lines=""
  n=0
  while IFS=$'\t' read -r token rid state prot; do
    [[ -n "$token" && "$token" != "-" ]] || continue
    n=$(( n + 1 ))
    if [[ "$rid" == "-" ]]; then rid_arg=""; mcp_rid=""; else rid_arg=" --run-id $rid"; mcp_rid=", run_id: \"$rid\""; fi
    lines="$lines"$'\n'"  lease token $token (owner run ${rid/#-/<none>}, $state, protected by $prot)"
    lines="$lines"$'\n'"    release: mcp__plugin_odoo-ai-agents_odoo-local__lease_release {lease_token: \"$token\"$mcp_rid}   |   park instead: mcp__plugin_odoo-ai-agents_odoo-local__lease_park {lease_token: \"$token\"$mcp_rid}"
    lines="$lines"$'\n'"    CLI fallback (only when the odoo-local tools are unavailable): python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py\" release $token$rid_arg   |   python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py\" park $token$rid_arg"
  done <<< "$rows"

  [[ "$n" -gt 0 ]] || return 1

  # Name what this turn actually did, so the fix is unambiguous for every shape: a declared status
  # needs the release or the handoff; a turn with no status needs the release AND the missing block.
  local claim
  if [[ -n "$STATUS_KEY" ]]; then
    claim="ended its dispatch on \`status: $STATUS_KEY\` with no \`INSTANCE_HANDLE\` forwarded"
  else
    claim='ended its dispatch with NO `status` in a closed `continuation` block (a SubagentStop IS the end of your dispatch - not a pause, and nothing runs later on your behalf)'
  fi

  # THREE exits satisfy this gate, and all three are named here on purpose. The set is the one
  # declared in snippets/resource-teardown-contract.md T1 section "The three exits" (SSOT); this is a
  # SECOND COPY of it, kept in lockstep by tests/test_enforce_teardown.py rather than rendered from
  # the markdown at hook time. Naming only `release` would tell an agent that preserving a
  # just-built database is impossible, which is how instances got destroyed and rebuilt every
  # dispatch.
  printf 'Resource-teardown gate: this subagent %s, but %d LIVE, non-shared instance lease(s) that THIS subagent obtained itself (acquired or adopted by your own calls - read from your own tool calls and their results, never from a run id and never from a lease_token you were handed and merely served or resumed, so a lease of your parent or a sibling is never listed here and is not yours to release) are still held in the allocator ledger. Each is a detached Odoo server process or database that outlives this dispatch until reclaimed. Clear EACH before your terminal status, by ONE of the three exits:%s\n1) release - stops the whole server process group, then drops the DB. 2) park the lease (`lease_park`, or `allocator.py park`; NOT the turn-parking discipline of the same name) - stops the same process group (so the RAM is freed) but KEEPS the database, filestore and ports, so a later dispatch resumes it instead of rebuilding; use it when the DB is still wanted - park DEFERS the eventual drop, it never cancels it, and it reports the drop_on_release flag it left untouched so you can see whether the final release will still destroy that DB. 3) handoff - forward INSTANCE_HANDLE in your continuation `next.inputs` to a NAMED catcher, which leaves the instance running for it. Then report a `continuation` block whose `status` is one of the contract values. If exits 1 and 2 are UNAVAILABLE to you - the allocator errored, a process refuses to die, or the HARNESS DENIED the give-back call before it ran - do NOT fall back to a bare stopped-run report. Exit 3 is always available: it is text in your own continuation fence, needs no tool, no permission and no live process, and when teardown is what failed the named catcher is your DISPATCHING CALLER. Forward INSTANCE_HANDLE (lease_token + run_id) in next.inputs to it, state in your report that teardown was denied and quote the exact refusal, and keep your BLOCKED or NEEDS_CONTEXT status - the status is not what this gate reads.' \
    "$claim" "$n" "$lines"
  return 0
}

if REASON="$(_instance_block_reason)"; then
  # Surface any browser finding inside the same block so the agent fixes both at once.
  [[ -n "$BROWSER_MSG" ]] && REASON="$REASON"$'\n\nAlso (advisory, browser): '"$BROWSER_MSG"
  jq -cn --arg r "$REASON" '{decision:"block", reason:$r}'
  exit 0
fi

# --- Browser advisory (both events, never blocks) --------------------------------------------
if [[ -n "$BROWSER_MSG" ]]; then
  jq -cn --arg m "Resource-teardown advisory (browser pages/recordings die with the session, so this is a nudge, not a block): $BROWSER_MSG." \
    '{continue:true, systemMessage:$m}'
  exit 0
fi

_pass
