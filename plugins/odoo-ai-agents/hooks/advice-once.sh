# advice-once.sh - SOURCED helper (not a hook): the ONE implementation of "is this advice already
# in the agent's context". Every ADVISORY hook asks it before emitting, so a reminder lands once per
# context window instead of on every prompt, tool call or turn end - detect-intent.sh,
# remind-delegate.sh, drive-continuation.sh, enforce-teardown.sh's browser advisory and
# enforce-grounding.sh's notes.
#
# On Stop / SubagentStop it is also the LOOP GUARD (_stop_text_due below): the harness runs one more
# model turn for every Stop / SubagentStop that emits additionalContext or a block (measured on
# Stop: six emissions in a row, six extra turns), so a text re-emitted on every turn end would never
# let the agent stop. Said once, the agent that chooses to stay stopped is left alone.
#
# WHY IT EXISTS: an advisory that is already in the context costs tokens again every time it is
# repeated, tells the model nothing new, and every copy stays in the context. A hook has no memory
# of its own between calls, so it asks the one record that has: the transcript.
#
# WHERE "already said" IS READ FROM: the transcript the payload names. The harness records every
# hook's text there (an `attachment` record - hook_additional_context for additionalContext, which
# the model reads, hook_system_message for systemMessage, which it does not - carrying the text
# verbatim, JSON-escaped once). The match is on the text, whatever the record type. Only the
# CURRENT CONTEXT WINDOW counts: the records after the last `compact_boundary` record. Compaction
# drops earlier attachments from the context, so advice said before it is said again once after it -
# which a marker file kept outside the transcript could not know. A new session (or /clear) is a new
# transcript, so it starts empty.
#
# Fails OPEN to "not seen" (the advice is emitted, the old behaviour) on any uncertainty: no
# transcript, an unreadable one, an empty text. A Stop / SubagentStop caller therefore needs a second
# guard for the no-transcript case (stop_hook_active), or a missing transcript becomes a loop.
#
# Accepted residual: the harness runs the PreToolUse hooks of several tool calls issued in ONE
# message before it records any of their output, so each of them can still emit the same advisory
# once - a few copies once per context window, not one per call. Closing it would need state kept
# outside the transcript, which compaction does not reset.

# The records of the current context window, in ANY order: from the end of the transcript back to
# the last compact_boundary record (tac reads backwards and stops there), else - no tac - forward
# from that record. The boundary is matched on its raw record key: inside any message text the same
# characters are JSON-escaped (\"subtype\"), so quoted text never looks like a boundary.
_ADVICE_BOUNDARY_RE='"subtype"[[:space:]]*:[[:space:]]*"compact_boundary"'
_advice_window() {
  local transcript="$1" n
  [[ -n "$transcript" && -r "$transcript" ]] || return 0
  if command -v tac >/dev/null 2>&1; then
    tac -- "$transcript" 2>/dev/null | sed "/${_ADVICE_BOUNDARY_RE}/q" 2>/dev/null
  else
    n="$(grep -n -e "$_ADVICE_BOUNDARY_RE" -- "$transcript" 2>/dev/null | tail -n 1 | cut -d: -f1)"
    tail -n +"${n:-1}" -- "$transcript" 2>/dev/null
  fi
  return 0
}

# A text as it appears inside a JSON string in the transcript (escaped once). Raw UTF-8 stays raw,
# as the harness writes it. jq when present; otherwise backslash, double quote and newline - all an
# advisory text carries (awk's handling of backslashes in a gsub replacement differs between
# implementations, so the backslash work is sed's).
_advice_json_escape() {
  if command -v jq >/dev/null 2>&1; then
    printf '%s' "$1" | jq -Rrs 'tojson | .[1:-1]' 2>/dev/null
  else
    printf '%s\n' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' \
      | awk 'BEGIN { ORS = "" } { print (NR > 1 ? "\\n" : "") $0 }'
  fi
}

# $1 = transcript, $2.. = advice texts. Prints the 0-based index of every text NOT already in the
# current context window, one per line, in argument order - the ones the caller should emit. One
# pass over the window for all of them. An empty text is never reported (nothing to emit).
_advice_unseen() {
  local transcript="$1"; shift
  [[ $# -gt 0 ]] || return 0
  local -a esc=()
  local t i found=""
  for t in "$@"; do esc+=("$(_advice_json_escape "$t")"); done
  if [[ -n "$transcript" && -r "$transcript" ]]; then
    local pats
    pats="$(for t in "${esc[@]}"; do [[ -n "$t" ]] && printf '%s\n' "$t"; done)"
    if [[ -n "$pats" ]]; then
      found="$(_advice_window "$transcript" | grep -o -F -e "$pats" 2>/dev/null | sort -u)"
    fi
  fi
  for i in "${!esc[@]}"; do
    [[ -n "${esc[$i]}" ]] || continue
    if [[ -n "$found" ]] && printf '%s\n' "$found" | grep -qxF -- "${esc[$i]}" 2>/dev/null; then
      continue
    fi
    printf '%s\n' "$i"
  done
  return 0
}

# rc 0 when the one text $2 already sits in the current context window of transcript $1.
_advice_seen() {
  [[ -z "$(_advice_unseen "$1" "$2")" ]]
}

# rc 0 when a Stop / SubagentStop ADVISORY $3 is due now: it is not yet in the current context window
# of transcript $1. With no readable transcript there is no record of what was said, so it is due
# only on a stop no hook continued ($2 = the payload's stop_hook_active): a missing transcript must
# never turn into a loop. An advisory said once in the window is not said again - it would tell the
# agent nothing new.
_stop_text_due() {
  local transcript="$1" active="$2" text="$3"
  if [[ -n "$transcript" && -r "$transcript" ]]; then
    ! _advice_seen "$transcript" "$text"
  else
    [[ "$active" != "true" ]]
  fi
}

# The jq test for a record that starts a TURN of the agent from outside the hooks: its first prompt
# (a plain user string), or a wake recorded as a meta user string with an origin - a caller
# resuming the stopped agent (`coordinator`, `peer`) or a background completion
# (`task-notification`). A hook's block ("Stop hook feedback:", a meta user string with no origin)
# and a hook's additionalContext (an attachment) are not, and neither is a tool_result (a list).
# Measured on Claude Code 2.1.288.
_STOP_TURN_START_JQ='(.type == "user") and (((.message // {}).content | type) == "string")
  and ((.isMeta != true) or ((.origin.kind // "") | IN("coordinator", "peer", "task-notification")))'

# rc 0 when the HARD-BLOCK reason $3 is due now. On a stop no hook continued ($2 = stop_hook_active
# false) it is ALWAYS due: that report is new - a caller resumed the agent, or it is its first stop -
# and a reason given in an earlier round says nothing about it. On a hook-continued stop it is due
# unless it was already given in THIS chain - since the turn began (the last turn-start record) and
# since the last compaction - so a block the agent ignores is not repeated forever, while a reason
# first met in a turn a note bought still fires. No readable transcript -> due only on a fresh stop.
# Unknown shape (no jq, no turn-start record found) -> the whole context window, as for advisories.
_stop_block_due() {
  local transcript="$1" active="$2" text="$3" start compact esc
  [[ "$active" == "true" ]] || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || return 1
  start=""
  if command -v jq >/dev/null 2>&1; then
    start="$(jq -nRr "reduce (inputs | (fromjson? // null)) as \$r ({n: 0, at: null};
      .n += 1 | if (\$r | type) == \"object\" and (\$r | $_STOP_TURN_START_JQ) then .at = .n else . end)
      | .at // empty" < "$transcript" 2>/dev/null || true)"
  fi
  [[ "$start" =~ ^[0-9]+$ ]] || { ! _advice_seen "$transcript" "$text"; return; }
  compact="$(grep -n -e "$_ADVICE_BOUNDARY_RE" -- "$transcript" 2>/dev/null | tail -n 1 | cut -d: -f1)"
  [[ "$compact" =~ ^[0-9]+$ && "$compact" -gt "$start" ]] && start="$compact"
  esc="$(_advice_json_escape "$text")"
  [[ -n "$esc" ]] || return 0
  ! tail -n +"$start" -- "$transcript" 2>/dev/null | grep -qF -- "$esc"
}
