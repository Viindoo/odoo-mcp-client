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
#     END - a completion claim, `NEEDS_NEXT` with no handle forwarded, an out-of-enum
#     status, or NO `continuation` status at all - is a HARD BLOCK (SubagentStop only)
#     with a deterministic release cmd. Only a stopped-run report (BLOCKED /
#     NEEDS_CONTEXT) or a T4 named handoff passes. A lease the caller PARKED is not a
#     live lease at all for this purpose: park already stopped its process group, so it
#     leaks no RAM, and it carries `parked_at` - the ledger fact the ledger scan below
#     filters on. Its three exits (release / park / forwarded INSTANCE_HANDLE) are the
#     ones the block message names.
#   - BROWSER pages die WITH the session's MCP server process - a bounded, self-
#     healing leak. Their count is only inferable from the transcript (open/close
#     calls), which is fuzzy. So browser findings are ADVISORY ONLY (systemMessage,
#     NEVER decision:block) on both SubagentStop and Stop - prevention + a nudge.
#
# CONTRACT (Claude Code Stop / SubagentStop): stdin JSON has transcript_path,
# stop_hook_active, hook_event_name.
#   - Self-gates (clone of enforce-grounding.sh): missing jq / missing transcript
#     / stop_hook_active=true / a non-teardown-shaped subagent -> silent exit 0.
#   - Block form (instances, SubagentStop only): {"decision":"block","reason":...}.
#   - Advisory form (browsers): {"continue":true,"systemMessage":...}.
#   - Degrades to exit 0 on ANY uncertainty (no jq/python3/ledger, parse error,
#     ambiguous run_id). This is the ONLY hard-block gate in the system: a false
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

TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
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

# --- run_id correlation (ONLY from the subagent's OWN owning-action allocator commands) -------
# The SubagentStop stdin carries no allocator run_id, so we derive it STRICTLY from the run-id
# this subagent itself threaded into one of its OWN owning-action allocator Bash calls - the
# provisioner/owner verbs `acquire` / `bind` / `heartbeat` (the ones that carry --run-id). This
# is proof the subagent PROVISIONED or OWNS the lease. We deliberately do NOT scan free assistant
# text (a bare `run_id: <X>`): a compliant CONSUMER of a forwarded INSTANCE_HANDLE quotes that
# run_id in its own report (per agents/odoo-qa-tester.md's "this was forwarded to me, I am NOT
# releasing it") - scanning text would HARD-BLOCK that consumer on the one blocking gate in the
# system. `release` is also excluded: a release attempt is not an ownership claim, and if it
# succeeded the ledger check below already reflects reality. An empty run_id is never a key.
_run_ids() {
  # $'^CALL\t' (ANSI-C quoting) anchors on a REAL tab so only genuine tool_use CALL lines match -
  # never a command quoted inside assistant prose (a TEXT line, or a wrapped text continuation).
  printf '%s\n' "$NORM" \
    | grep -E $'^CALL\t' \
    | grep -E 'allocator\.py' \
    | grep -E '(^|[[:space:]])(acquire|bind|heartbeat)([[:space:]]|$)' \
    | grep -oE -- '--run-id[[:space:]=]+[A-Za-z0-9._-]+' \
    | sed -E 's/^--run-id[[:space:]=]+//' \
    | grep -vE '^$' | sort -u 2>/dev/null || true
}
RUN_IDS="$(_run_ids)"

# Self-gate (clone of enforce-grounding.sh's "non-Odoo subagent" gate): no browser activity AND
# no run-id signal -> not a teardown-shaped subagent -> stay out of the way.
if [[ "$BROWSER_ANY" -eq 0 && -z "$RUN_IDS" ]]; then
  _pass
fi

# --- Instance check: BLOCKING, SubagentStop only, stop-report + named handoff excepted --------
# Fires on a subagent turn that neither reported a stopped run nor forwarded its handle by name.
# Ground truth is the LEDGER (via the allocator's own `list` read command), never the transcript.
# Emits the ONE hard block in the system; everything above is advisory.
_instance_block_reason() {
  # Requires: SubagentStop event, python3 + allocator.py, a correlated run_id, no forwarded
  # handle. Prints the block reason on success; prints nothing (rc!=0) to fall through to advisory.
  [[ "$EVENT" == "SubagentStop" ]] || return 1
  # Gate on the COMPLEMENT of a STOPPED-RUN REPORT - NEVER on the literal `DONE`. `status` is a
  # CLOSED four-value enum (SSOT: generator/skill_tool_deps.json `vocabulary.continuation_status`,
  # rendered in snippets/continuation-contract.md) and only these two report a run that STOPPED:
  # resource-teardown-contract.md T4 makes BLOCKED the sanctioned outcome when teardown ITSELF
  # failed ("report the lease token ... so the caller or allocator GC can reap it"), so blocking
  # them would trap the one path the contract gives that failure. Everything else is a dispatch
  # that ENDED while the ledger still holds this run's lease and falls through to the T4 handoff
  # test below: `DONE`, `NEEDS_NEXT` (T4 permits a live lease under it ONLY with the handle
  # forwarded - a bare one is the "unnamed forward the token for later release" T4 names as the
  # leak), a value outside the enum, or NO machine-readable `continuation` status at all (that one
  # leaks worst - no status means no fence, so no forwarded handle and no named catcher either,
  # and a SubagentStop IS the end of the dispatch, so nothing runs later to release it). Same
  # case-with-catch-all shape as report-terminal-status.sh's S1 strand signature, which already
  # COUNTS the no-status turn - this gate is what stops the leak it counts.
  case "$STATUS_KEY" in
    BLOCKED|NEEDS_CONTEXT) return 1 ;;
  esac
  # T4's ONE exception, read from the SAME fence-scoped extraction as the status (never from free
  # prose - a handle promised in prose forwards nothing a consumer can act on).
  [[ "$FWD_HANDLE" == "1" ]] && return 1   # INSTANCE_HANDLE forwarded in next.inputs -> handoff -> pass
  [[ -n "$RUN_IDS" ]] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  local alloc="${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/allocator.py"
  [[ -n "${CLAUDE_PLUGIN_ROOT:-}" && -f "$alloc" ]] || return 1

  local ledger
  ledger="$(timeout 5 python3 "$alloc" list --show-tokens 2>/dev/null || true)"
  [[ -n "$ledger" ]] || return 1

  local rids_json now
  rids_json="$(printf '%s\n' "$RUN_IDS" | jq -R . | jq -cs . 2>/dev/null || true)"
  [[ -n "$rids_json" && "$rids_json" != "null" ]] || return 1
  now="$(date +%s 2>/dev/null || echo 0)"

  # EVERY LIVE, non-shared, NON-PARKED lease owned by one of our run_ids. A PARKED lease
  # (`parked_at` present) is skipped, and skipping it is the point rather than a hole: park already
  # DID the RAM half of teardown - it stops the owner's whole process group BEFORE clearing the pid
  # - and what survives is disk (the database, the filestore, the port reservation) under the
  # allocator's own park budget. Without this the gate would read a parked lease as "no pid, fresh
  # ttl" and hard-block the very subagent that parked it, telling it to release the instance it
  # deliberately preserved - i.e. it would refuse the exit it is meant to permit. The exemption
  # cannot outlive the park because `allocator.py resume` DELETES `parked_at` as part of the same
  # locked compare-and-set that writes the new owner pid: a resumed lease is a pid-carrying lease
  # again and is gated here again. LIVE-ness mirrors
  # allocator's `_is_stale`: a recorded pid on THIS host is
  # AUTHORITATIVE - alive protects the lease regardless of ttl, dead condemns
  # it regardless of ttl. Only when liveness cannot be checked here at all (a
  # different host, or no pid recorded) does ttl/heartbeat freshness decide -
  # the ONE case ttl still governs, same scope as the real `_is_stale`. This
  # hook intentionally skips the allocator's pid-recycling fingerprint proof
  # (`owner.pid_started`): recycling within ONE subagent's own short dispatch
  # window (this hook only asks "is the lease this transcript just acquired
  # still the same live process moments later") is not a practical risk the
  # way it is for allocator.py's cross-session `gc`, so a bare `kill -0` here
  # is an accepted simplification, not a drift from the real rule. We report
  # ALL live leases (a run can hold more than one), each with its own release
  # command, so the blocked agent can clear every leak deterministically in
  # one pass.
  # NOTE on the TSV shape below: every field is forced NON-EMPTY (pid/host fall
  # back to the literal "null" via bare `tostring`, never a raw ""). `read`
  # with a whitespace IFS (tab included) silently SQUASHES a truly-empty field
  # in the middle of a row into its neighbour - the pid-less lease is the
  # common case (most leases never carry --pid), so an empty pid field here
  # would misalign every column after it. Never reintroduce a `// ""` fallback
  # on a middle TSV field for this reason.
  # The `// 3600` fallback below is a SECOND COPY of `DEFAULT_TTL_S` in
  # scripts/lib/allocator.py (the SSOT) - it only ever fires for a lease
  # record missing `ttl_s` entirely (defensive; every real acquire writes it).
  # If that constant changes, this literal must change with it or the two
  # staleness checks silently disagree on the one lease shape neither writer
  # normally produces.
  local rows
  rows="$(printf '%s' "$ledger" | jq -r \
    --argjson rids "$rids_json" --argjson now "$now" '
      .leases[]?
      | select((.mode // "") != "shared")
      | select(has("parked_at") | not)
      | ((.owner.run_id // .owner.session_id // "")) as $o
      | select($o != "" and ($rids | index($o)))
      | [(.token // ""), $o, (.owner.pid | tostring), (.owner.host | tostring),
         ((($now - (.heartbeat_at // .owner.started_at // 0)) <= (.ttl_s // 3600)) | tostring)]
      | @tsv' 2>/dev/null || true)"
  [[ -n "$rows" ]] || return 1

  local this_host lines n token rid pid host ttl_fresh live
  this_host="$(hostname 2>/dev/null || echo _nohost_)"
  lines=""
  n=0
  while IFS=$'\t' read -r token rid pid host ttl_fresh; do
    [[ -n "$token" ]] || continue
    live=0
    if [[ -n "$pid" && "$pid" != "null" && "$host" == "$this_host" ]]; then
      # _is_stale pid arm: alive on this host -> protected regardless of ttl;
      # dead -> condemned regardless of ttl (prefer false-negative: skip it).
      kill -0 "$pid" 2>/dev/null && live=1
    elif [[ "$ttl_fresh" == "true" ]]; then
      # liveness unprovable here (different host, or no pid recorded) -> ttl governs.
      live=1
    fi
    [[ "$live" == "1" ]] || continue
    n=$(( n + 1 ))
    lines="$lines"$'\n'"  lease token $token (owner run $rid) -> release: python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py\" release $token --run-id $rid   |   park instead: python3 \"\${CLAUDE_PLUGIN_ROOT}/scripts/lib/allocator.py\" park $token"
  done <<< "$rows"

  [[ "$n" -gt 0 ]] || return 1   # nothing live to block on (dead-pid rows and expired-unprovable rows skipped)

  # Name what this turn actually did, so the fix is unambiguous for every shape: a declared status
  # needs the release or the handoff; a turn with no status needs the release AND the missing block.
  local claim
  if [[ -n "$STATUS_KEY" ]]; then
    claim="ended its dispatch on \`status: $STATUS_KEY\` with no \`INSTANCE_HANDLE\` forwarded"
  else
    claim='ended its dispatch with NO `status` in a closed `continuation` block (a SubagentStop IS the end of your dispatch - not a pause, and nothing runs later on your behalf)'
  fi

  # THREE exits satisfy this gate, and all three are named here on purpose. The set is the one
  # declared in snippets/resource-teardown-contract.md T1 § "The three exits" (SSOT); this is a
  # SECOND COPY of it, exactly like the `// 3600` DEFAULT_TTL_S copy above, kept in lockstep by
  # tests/test_enforce_teardown.py rather than rendered from the markdown at hook time. Naming only
  # `release` would tell an agent that preserving a just-built database is impossible, which is how
  # instances got destroyed and rebuilt every dispatch.
  printf 'Resource-teardown gate: this subagent %s, but %d LIVE, non-shared instance lease(s) owned by this run are still held in the allocator ledger. Each is a detached Odoo server process that outlives this session and leaks RAM until reclaimed. Clear EACH before your terminal status, by ONE of the three exits:%s\n1) release - stops the whole server process group, then drops the DB. 2) park the lease (`allocator.py park`, NOT the turn-parking discipline of the same name) - stops the same process group (so the RAM is freed) but KEEPS the database, filestore and ports, so a later dispatch resumes it instead of rebuilding; use it when the DB is still wanted. 3) handoff - forward INSTANCE_HANDLE in your continuation `next.inputs` to a NAMED catcher, which leaves the instance running for it. Then report a `continuation` block whose `status` is one of the contract values.' \
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
