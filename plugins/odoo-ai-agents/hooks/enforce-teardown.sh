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
#     from the ledger (released or parked), or a T4 named handoff forwards THAT lease's
#     `INSTANCE_HANDLE` (its own lease_token, in next.inputs - per lease: one forwarded handle
#     never clears a second live lease). The gate is STATUS-BLIND on purpose: a dispatch that cannot
#     RELEASE can always still NAME a catcher, so `BLOCKED` is no longer a door the
#     lease escapes through unowned. A lease the caller PARKED is not a
#     live lease at all for this purpose: park already stopped its process group, so it
#     leaks no RAM, and the allocator's verdict reports it as `state: parked`. Its three
#     exits (release / park / forwarded INSTANCE_HANDLE) are the ones the block message
#     names - except after a DELIVERED SubagentHandback, when the report and its fence are final
#     (a second handback is refused, and R3 forbids carrying a report in any other message), so the
#     block names release and park only.
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
#     A chrome-devtools page counts as DRIVEN whether this agent opened it (new_page)
#     or reused one (navigate_page); the server refuses to close its last page, so
#     the rule nudged here is "close every page but one, then navigate that one to
#     about:blank". Where the calls carry a pageId (page-id routing, on by default since
#     chrome-devtools-mcp 1.10) it is judged PER PAGE: every page whose last navigation was not
#     about:blank and that was not closed afterwards is named. A call without a pageId falls back
#     to the URL of the last new_page / navigate_page call.
#
# CONTRACT (Claude Code Stop / SubagentStop): stdin JSON has transcript_path,
# stop_hook_active, hook_event_name; SubagentStop also carries agent_transcript_path.
#   - WHICH transcript: on SubagentStop `agent_transcript_path` (the subagent's OWN
#     transcript). The payload's `transcript_path` is the WHOLE session's (the parent
#     plus every sibling), so reading it attributed the parent's acquires and browser
#     pages to whichever subagent stopped next. It is read only on Stop, where the
#     session transcript IS the stopping agent's. Same rule, same reason as
#     enforce-background-wait.sh.
#   - WHICH text is the report: the one the caller actually received - the message of a
#     DELIVERED `SubagentHandback` call, else the final message (the payload's
#     last_assistant_message; hooks/final-report.sh). The status and the forwarded handles are read from that
#     report's closed continuation fence, never from assistant text the caller never saw.
#   - A stop that WAITS is not the end of the dispatch. On a surface that wakes a stopped subagent
#     once per teammate it launched (any surface but the unattended one - the same surface test
#     enforce-background-wait.sh applies), a coordinator ends its turn to wait for a teammate while
#     it still holds its node lease for the work it resumes (snippets/spawner-completion-contract.md
#     R0 move 3). So a SubagentStop whose payload still lists, running, a teammate THIS subagent
#     launched asynchronously (hooks/teammate-wait.sh - the wait gate's own correlation) is not
#     gated, unless a report was already DELIVERED through SubagentHandback (a real final report:
#     gated as always). Residual: an unattended surface that exports neither surface signal is
#     read as one that wakes, and its lease then outlives the stop until the SessionEnd backstop.
#   - A report handed back through SubagentHandback is delivered BEFORE this hook runs, so this
#     block alone arrives too late for it. block-handback-with-live-lease.sh (PreToolUse) runs the
#     SAME check (hooks/teardown-check.sh) at the handback itself; this gate remains the backstop
#     for a lease obtained after the handback and for a report delivered as plain text.
#   - Self-gates (clone of enforce-grounding.sh): missing jq / missing transcript
#     / stop_hook_active=true / a non-teardown-shaped subagent -> silent exit 0.
#   - Block form (instances, SubagentStop only): {"decision":"block","reason":...}.
#   - Advisory form (browsers): {"continue":true,"systemMessage":...}.
#   - Degrades to exit 0 on ANY uncertainty (no jq/python3/allocator, parse error,
#     no verdict, no correlated token, an unreadable shared helper). A hard-block gate: a false
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

# Shared helpers: hooks/final-report.sh (which transcript, what the agent REPORTED, its fence) and
# hooks/teardown-check.sh (the allocator-verdict check and its refusal). Resolved relative to THIS
# script. Either unreadable -> fail open, the convention every hook in this plugin follows.
_HOOK_DIR="${BASH_SOURCE[0]%/*}"
for _lib in final-report.sh teardown-check.sh lease-correlation.sh teammate-wait.sh; do
  [[ -r "$_HOOK_DIR/$_lib" ]] || _pass
  # shellcheck source=/dev/null
  . "$_HOOK_DIR/$_lib"
done

# The subagent's OWN transcript on SubagentStop; the session transcript only on Stop (see
# CONTRACT). A SubagentStop without agent_transcript_path is uncertainty -> pass, never a
# fallback onto the session transcript (that fallback IS the defect).
TRANSCRIPT="$(_hook_transcript "$INPUT")"
[[ -n "$TRANSCRIPT" ]] || _pass

# --- The subagent's own activity (ASSISTANT-authored only) -----------------------------------
# Tool CALLS are counted from real `tool_use` blocks - never from an injected brief/tool_result
# that quotes a tool name. One "CALL\t<name>\t<command-or-path>" line per call (final-report.sh
# _assistant_signals).
LAST_MESSAGE="$(_hook_last_message "$INPUT")"
NORM="$(_assistant_signals "$TRANSCRIPT" "$LAST_MESSAGE")"

_cnt() { printf '%s\n' "$NORM" | grep -ciE "$1" 2>/dev/null | tr -d '[:space:]' || true; }

# --- Browser matcher (SUFFIX-keyed across ALL prefix namespaces) -----------------------------
# Names look like mcp__chrome-devtools__new_page / mcp__chrome-devtools-headed__new_page /
# mcp__plugin_odoo-ai-agents_chrome-devtools__new_page / playwright + pagecast + -headed +
# plugin_* variants. Key ONLY on the trailing __<name>, never a fixed server prefix, so a new
# namespace is matched for free. Each CALL line is "CALL\t<name>\t<cmd>"; `[^\t]*__<name>\t`
# anchors on the name field ending in __<name>.

# chrome-devtools: OPEN = new_page, CLOSE = close_page, DRIVE = new_page or navigate_page (a reused
# page is driven too). The last page cannot be closed, so it must end on about:blank. A
# navigate_page with no url (back / forward / reload) left the page on a real URL, so it is not
# about:blank. select_page / list_pages never count. The page calls in order, with pageId and url,
# come from final-report.sh _chrome_page_calls ("<op>\t<pageId>\t<url>").
NEW_PAGE=$(_cnt $'^CALL\t[^\t]*__new_page\t')
CLOSE_PAGE=$(_cnt $'^CALL\t[^\t]*__close_page\t')
CD_NAVIGATE=$(_cnt $'^CALL\t[^\t]*__navigate_page\t')
CD_DRIVE=$(( NEW_PAGE + CD_NAVIGATE ))
CD_PAGE_CALLS="$(_chrome_page_calls "$TRANSCRIPT")"
# The LAST new_page / navigate_page call: "<pageId>\t<url>". When it carries no pageId, its url is
# the one fallback signal for the page it left behind.
CD_LAST_DRIVE="$(printf '%s\n' "$CD_PAGE_CALLS" | awk -F'\t' '$1 == "new_page" || $1 == "navigate_page" { last = $2 "\t" $3 } END { printf "%s", last }' 2>/dev/null || true)"
CD_LAST_ID="${CD_LAST_DRIVE%%$'\t'*}"
CD_LAST_URL="${CD_LAST_DRIVE#*$'\t'}"
# Per page (calls that carry a pageId): each page whose last navigation is not about:blank and
# that no later close_page closed, as "<pageId> (<url>)", comma-separated, in first-driven order.
CD_LIVE_PAGES="$(printf '%s\n' "$CD_PAGE_CALLS" | awk -F'\t' '
  $2 == "" { next }
  $1 == "close_page" { delete last[$2]; next }
  { if (!($2 in seen)) { seen[$2] = 1; ids[++n] = $2 } last[$2] = $3 }
  END {
    for (i = 1; i <= n; i++) {
      id = ids[i]
      if (!(id in last) || last[id] == "about:blank") continue
      printf "%s%s (%s)", (shown++ ? ", " : ""), id, (last[id] == "" ? "back/forward/reload" : last[id])
    }
  }' 2>/dev/null || true)"

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

BROWSER_ANY=$(( CD_DRIVE + CLOSE_PAGE + PW_ALL + RECORD + STOP_REC ))

# Build the ADVISORY message (concrete unmatched counts). Never blocks.
BROWSER_MSG=""
_add_note() { if [[ -n "$BROWSER_MSG" ]]; then BROWSER_MSG="$BROWSER_MSG; $1"; else BROWSER_MSG="$1"; fi; }
[[ "$NEW_PAGE" -gt "$CLOSE_PAGE" ]] && \
  _add_note "$NEW_PAGE new_page vs $CLOSE_PAGE close_page - close every chrome-devtools page but one before your terminal status (list_pages, then close_page each extra page)"
[[ -n "$CD_LIVE_PAGES" ]] && \
  _add_note "chrome-devtools: page(s) $CD_LIVE_PAGES left on a non-blank URL and not closed - close_page every page but one and navigate_page the one you keep to about:blank before your terminal status"
[[ "$CD_DRIVE" -gt 0 && -z "$CD_LAST_ID" && "$CD_LAST_URL" != "about:blank" ]] && \
  _add_note "chrome-devtools: your last navigation left a page on ${CD_LAST_URL:-a non-blank page} - navigate_page the page you keep to about:blank before your terminal status"
[[ "$PW_DRIVE" -gt 0 && "$PW_CLOSE" -eq 0 && "$PW_TABS" -eq 0 ]] && \
  _add_note "playwright: $PW_DRIVE driving call(s) with 0 browser_close - one browser_close closes everything you drove; call it before your terminal status"
[[ "$PW_SVIDEO" -gt "$PW_EVIDEO" ]] && \
  _add_note "$PW_SVIDEO browser_start_video vs $PW_EVIDEO browser_stop_video - stop the video before your terminal status"
[[ "$PW_STRACE" -gt "$PW_ETRACE" ]] && \
  _add_note "$PW_STRACE browser_start_tracing vs $PW_ETRACE browser_stop_tracing - stop tracing before your terminal status"
[[ "$RECORD" -gt "$STOP_REC" ]] && \
  _add_note "$RECORD record_page vs $STOP_REC stop_recording - stop the pagecast recording before your terminal status"

# --- Continuation status + INSTANCE_HANDLE forwarding (the REPORT only) ----------------------
# Read from the report the caller actually received (final-report.sh _final_report_text): the
# delivered SubagentHandback message, else the final message
# (the payload's last_assistant_message - the transcript file may not hold it yet).
# Then the body of its LAST CLOSED ```continuation block, and status + the per-lease handle
# forwarding (next.inputs) from that body. A single captured block means an INSTANCE_HANDLE mentioned in prose OUTSIDE the block, or
# in an earlier turn the caller never received, never counts as a forward.
REPORT="$(_final_report_text "$TRANSCRIPT" "$LAST_MESSAGE")"
CONT_BLOCK="$(_continuation_block "$REPORT")"
STATUS="$(_continuation_status "$CONT_BLOCK")"
# The gate below blocks the COMPLEMENT of a small allowed set, so a cosmetic spelling must never be
# what turns a declared status into a hard block: compare the normalized KEY. Empty = no status.
STATUS_KEY="$(_continuation_status_key "$STATUS")"
# The stopping subagent's own id - its own `background_tasks` entry is never one of its teammates.
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
# Was the report already DELIVERED through the SubagentHandback tool? Then a second handback is
# refused by the harness, and the block below must not send the agent to hand back again.
HANDED_BACK=0
_handback_delivered "$TRANSCRIPT" && HANDED_BACK=1

# --- Token correlation (ONLY leases THIS subagent itself obtained) ----------------------------
# "Which leases did THIS dispatch obtain?" is answered by hooks/lease-correlation.sh, the ONE
# implementation this gate shares with block-unowned-lease-mutation.sh (read its header for exactly
# which calls count, and why serving or resuming a forwarded token and a time window never do). A
# shared copy is what keeps the two gates from disagreeing: this gate orders a release that the
# mutation gate must then allow. Helper unreadable -> no correlated token -> fail open.
OWN_TOKENS=""
declare -F _lease_owned_tokens >/dev/null 2>&1 && OWN_TOKENS="$(_lease_owned_tokens "$TRANSCRIPT")"
# The handoff is PER LEASE: each obtained token the report's fence forwards in its OWN
# INSTANCE_HANDLE (next.inputs) has a named catcher; every other one is still this dispatch's.
UNFWD_TOKENS="$(_continuation_unforwarded_tokens "$CONT_BLOCK" "$OWN_TOKENS")"

# Self-gate (clone of enforce-grounding.sh's "non-Odoo subagent" gate): no browser activity AND
# no lease this subagent obtained -> not a teardown-shaped subagent -> stay out of the way. A pure
# CONSUMER of a forwarded INSTANCE_HANDLE lands here: it obtained nothing, whatever it quotes.
if [[ "$BROWSER_ANY" -eq 0 && -z "$OWN_TOKENS" ]]; then
  _pass
fi

# --- Instance check: BLOCKING, SubagentStop only, named handoff excepted ----------------------
# The allocator-verdict check and its refusal text live in hooks/teardown-check.sh, shared with
# block-handback-with-live-lease.sh (the PreToolUse gate that stops the same lease from riding out
# inside a SubagentHandback report, which is delivered BEFORE this hook runs). This is the hard
# block; the browser findings above are advisory.
_instance_block_reason() {
  # Requires: SubagentStop event, a correlated token whose own handle the report does not forward,
  # and the allocator's verdict that the lease is live. Prints the block reason on success; nothing (rc!=0) otherwise.
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
  # Per lease: forwarding ONE lease's handle clears that lease only, never its siblings.
  [[ -n "$UNFWD_TOKENS" ]] || return 1   # every obtained lease forwarded in next.inputs -> handoff -> pass

  # A WAIT, not the end of the dispatch (see CONTRACT): a teammate this subagent launched is still
  # running and this surface wakes the subagent when it finishes, so the lease is still in use. A
  # report already delivered through SubagentHandback is final whatever is still running.
  if [[ "$HANDED_BACK" != "1" ]] && ! _tw_unattended \
     && [[ -n "$(_tw_own_live_teammates "$INPUT" "$AGENT_ID" "$TRANSCRIPT")" ]]; then
    return 1
  fi

  # Name what this turn actually did, so the fix is unambiguous for every shape: a declared status
  # needs the release or the handoff; a turn with no status needs the release AND the missing block.
  local claim closing=""
  if [[ -n "$STATUS_KEY" ]]; then
    claim="ended its dispatch on \`status: $STATUS_KEY\` with no \`INSTANCE_HANDLE\` forwarded for the lease(s) below"
  else
    claim='ended its dispatch with NO `status` in a closed `continuation` block (a SubagentStop IS the end of your dispatch - not a pause, and nothing runs later on your behalf)'
  fi
  # A report already handed back cannot be handed back again (the harness refuses a second
  # SubagentHandback) and nothing else may carry it (R3), so its fence - handoff included - is
  # final: only release or park is offered (`give-back`), never the handoff or a new report.
  local exits=all
  if [[ "$HANDED_BACK" == "1" ]]; then
    exits=give-back
    closing='Your report was ALREADY handed back through SubagentHandback, so it is final: a second SubagentHandback is refused, nothing can be added to its continuation fence, and no other message may carry it or an amendment, whatever that refusal suggests (snippets/spawner-completion-contract.md R3). To clear this lease now, release or park is the only way. If both are refused, stop anyway: nothing you write now reaches your caller, and the lease is reclaimed when this session ends.'
  fi
  _teardown_block_reason "$UNFWD_TOKENS" "$claim" "$closing" "$exits"
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
