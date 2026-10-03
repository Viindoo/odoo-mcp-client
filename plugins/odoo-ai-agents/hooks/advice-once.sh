# advice-once.sh - SOURCED helper (not a hook): the ONE implementation of "is this advice already
# in the agent's context". Every ADVISORY hook that injects text into the model's context
# (additionalContext / systemMessage) asks it before emitting, so a reminder lands once per context
# window instead of on every prompt, tool call or turn end - detect-intent.sh, remind-delegate.sh,
# drive-continuation.sh and enforce-teardown.sh's browser advisory.
#
# WHY IT EXISTS: an advisory that is already in the context costs tokens again every time it is
# repeated, tells the model nothing new, and every copy stays in the context. A hook has no memory
# of its own between calls, so it asks the one record that has: the transcript.
#
# WHERE "already said" IS READ FROM: the transcript the payload names. The harness records every
# injected text there (an `attachment` record - hook_additional_context / hook_system_message -
# carrying the text verbatim, JSON-escaped once). Only the CURRENT CONTEXT WINDOW counts: the
# records after the last `compact_boundary` record. Compaction drops earlier attachments from the
# context, so advice said before it is said again once after it - which a marker file kept outside
# the transcript could not know. A new session (or /clear) is a new transcript, so it starts empty.
#
# Fails OPEN to "not seen" (the advice is emitted, the old behaviour) on any uncertainty: no
# transcript, an unreadable one, an empty text.

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
