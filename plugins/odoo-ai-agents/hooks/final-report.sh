# final-report.sh - SOURCED helper (not a hook): the ONE implementation of "what did this agent
# REPORT to its caller, and what does that report's continuation fence say". Every hook that reads a
# subagent's terminal status or forwarded INSTANCE_HANDLE sources it - enforce-teardown.sh,
# parse-continuation.sh, report-terminal-status.sh, enforce-grounding.sh and
# block-handback-with-live-lease.sh - so they can never disagree about which text is the report.
#
# WHY IT EXISTS: a subagent's report can travel in a TOOL CALL, `SubagentHandback`
# ({"message": "<report>"}), instead of as its last assistant text. The report then lives in
# `tool_use.input.message`, not in any text block, and every hook that read "assistant text only"
# saw no status, no fence and no INSTANCE_HANDLE in a perfectly good report. Real transcripts also
# store each content block of one assistant turn as its OWN record (a thinking record, then a text
# record), so "the last assistant record" can be a thinking-only record with no text at all.
#
# Every function prints to stdout and prints nothing on any failure (no jq, unreadable file, parse
# error). Callers treat "nothing" as uncertainty, never as proof.

# The transcript a Stop / SubagentStop / PreToolUse payload is about. On SubagentStop that is
# `agent_transcript_path` - the subagent's OWN transcript; the payload's `transcript_path` is the
# WHOLE session's (parent plus every sibling), and reading it attributes other agents' calls and
# text to whichever subagent stopped. A SubagentStop without `agent_transcript_path` prints
# nothing: falling back onto the session transcript IS the defect. Any other event reads
# `transcript_path` (on Stop the session transcript IS the stopping agent's).
_hook_transcript() {
  local input="$1" event p
  command -v jq >/dev/null 2>&1 || return 0
  event="$(printf '%s' "$input" | jq -r '.hook_event_name // empty' 2>/dev/null || true)"
  if [[ "$event" == "SubagentStop" ]]; then
    p="$(printf '%s' "$input" | jq -r '.agent_transcript_path // empty' 2>/dev/null || true)"
  else
    p="$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
  fi
  [[ -n "$p" && -f "$p" ]] && printf '%s\n' "$p"
  return 0
}

# The payload's `last_assistant_message` (Stop / SubagentStop): the text of the agent's final
# message, as the harness hands it to the hook. It is the ONLY reliable copy of that text: observed
# live, the transcript file on disk does NOT yet hold the final assistant record when SubagentStop
# runs (the hook's snapshot ended at the preceding tool_result), so a hook that reads only the file
# never sees the report's own fence. Prints nothing when absent.
_hook_last_message() {
  command -v jq >/dev/null 2>&1 || return 0
  printf '%s' "$1" | jq -r '.last_assistant_message // empty | if type == "string" then . else empty end' 2>/dev/null || true
}

# Shared jq prelude: every record of the transcript, in order, as {i, role, meta, content, tur}.
# Both on-disk shapes are read: the harness's {"type", "message": {"role", "content"}} and the bare
# {"role", "content"}. `tur` is the record's toolUseResult (the structured tool result).
_FR_JQ_RECORDS='
  def blocktext: if type == "string" then .
                 elif type == "array" then (map(select(type == "object" and .type == "text") | (.text // "")) | join("\n"))
                 else "" end;
  [split("\n")[] | fromjson? | objects] as $L
  | [ $L | to_entries[] | .key as $i | .value as $r | ($r.message // $r) as $m
      | {i: $i, role: ((($m.role // $r.type) // "") | tostring), meta: ($r.isMeta == true),
         content: ($m.content // []), tur: ($r.toolUseResult // null)} ] as $R
  # The FINAL TURN: every assistant record after the last non-meta user record (a tool_result
  # carrier or a real prompt). A meta record (a system reminder, hook feedback) does not end it.
  | ([ $R[] | select(.role == "user" and (.meta | not)) | .i ] | max // -1) as $last_user
  | [ $R[] | select(.role == "assistant" and .i > $last_user) ] as $tail
'

# Shared jq fragment (after $_FR_JQ_RECORDS): $sends = every SubagentHandback call with its
# message, $delivered = the SubagentHandback calls the harness DELIVERED - their
# tool_result is neither an error (a PreToolUse deny comes back as one) nor `success: false` (how a
# second handback is refused, since one report per dispatch is delivered).
_FR_JQ_DELIVERED='
  | [ $R[] | select(.role == "assistant") | .i as $i | .content
      | (if type == "array" then .[] else empty end)
      | select(type == "object" and .type == "tool_use"
               and (((.name // "") | tostring) == "SubagentHandback"))
      | {i: $i, id: (.id // ""), name: .name,
         msg: ((.input.message // "") | if type == "string" then . else tojson end)} ] as $sends
  | [ $R[] | .tur as $tur | .content | (if type == "array" then .[] else empty end)
      | select(type == "object" and .type == "tool_result")
      | {id: (.tool_use_id // ""),
         bad: ((.is_error == true)
               or ((($tur | type) == "object") and ($tur.success == false))
               or ((.content | blocktext) | test("\"success\"[[:space:]]*:[[:space:]]*false")))} ] as $res
  | [ $sends[] | select(.name == "SubagentHandback") | . as $s
      | select(($res | map(select(.id == $s.id and $s.id != ""))) as $m
               | ($m | length) > 0 and ($m | map(.bad) | any | not)) ] as $delivered
'

# The report this agent delivered to its caller, as one text:
#   - When a `SubagentHandback` call was DELIVERED ($delivered above), the first one's
#     `input.message` - the one report the harness hands over.
#   - Otherwise the agent's final message - what the caller receives when no handback was
#     delivered: $2 (the payload's last_assistant_message, _hook_last_message) when given, since
#     the file may not hold that record yet; else the text blocks of the FINAL TURN in the file
#     (see $tail above).
_final_report_text() {
  local transcript="$1" last="${2:-}"
  command -v jq >/dev/null 2>&1 || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || { printf '%s' "$last"; return 0; }
  jq -rRs --arg last "$last" "$_FR_JQ_RECORDS$_FR_JQ_DELIVERED"'
  | if ($delivered | length) > 0 then
      $delivered[0].msg
    elif ($last | length) > 0 then $last
    else
      [ $tail[] | .content | blocktext | select(length > 0) ] | join("\n")
    end
  ' "$transcript" 2>/dev/null || true
}

# The number of tool_use blocks in the agent's FINAL TURN that no tool_result anywhere answers - a
# call the agent fired and then stopped without (the strand signature report-terminal-status.sh
# counts). Prints an integer; nothing when the transcript holds no assistant record at all (nothing
# to judge) or on failure.
_final_turn_unresolved_count() {
  local transcript="$1"
  command -v jq >/dev/null 2>&1 || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || return 0
  jq -rRs "$_FR_JQ_RECORDS"'
  | if ([ $R[] | select(.role == "assistant") ] | length) == 0 then empty else
      ([ $R[] | .content | (if type == "array" then .[] else empty end)
         | select(type == "object" and .type == "tool_result") | (.tool_use_id // "")
         | select(length > 0) ]) as $resids
      | ([ $tail[] | .content | (if type == "array" then .[] else empty end)
           | select(type == "object" and .type == "tool_use") | (.id // "") | select(length > 0) ]
         - $resids) | length
    end
  ' "$transcript" 2>/dev/null || true
}

# The agent's own activity as one line per signal, ASSISTANT-authored only (a tool name or label
# quoted in a brief or a tool_result never counts):
#   CALL\t<tool name>\t<command | file_path | path>   one per tool_use (newlines squashed)
#   TEXT\t<line>                                     one per LINE of a text block, and of the
#                                                    `message` of a SubagentHandback call
# Every line of a text carries the TEXT prefix, so a `^TEXT\t...` pattern sees a label on any line,
# not only the first line of a block. $2 (optional, the payload's last_assistant_message) is added
# as TEXT lines too - the final message may not be in the file yet (see _hook_last_message).
_assistant_signals() {
  local transcript="$1" last="${2:-}"
  command -v jq >/dev/null 2>&1 || return 0
  [[ -n "$last" ]] && printf '%s\n' "$last" | awk '{ print "TEXT\t" $0 }'
  [[ -n "$transcript" && -r "$transcript" ]] || return 0
  jq -rRs "$_FR_JQ_RECORDS"'
  | def textlines: split("\n")[] | "TEXT\t" + .;
    $R[] | select(.role == "assistant") | .content
  | (if type == "array" then .[] else empty end) | select(type == "object")
  | if (.type == "tool_use") then
      ("CALL\t" + ((.name // "") | tostring) + "\t"
        + (((.input.command // .input.file_path // .input.path // "") | tostring) | gsub("\n"; " "))),
      (if (((.name // "") | tostring) == "SubagentHandback") then
         ((.input.message // "") | if type == "string" then . else tojson end | textlines)
       else empty end)
    elif (.type == "text") then ((.text // "") | tostring | textlines)
    else empty end
  ' "$transcript" 2>/dev/null || true
}

# The body of the LAST CLOSED ```continuation fenced block in a report text ("" when none). Only a
# closed block counts: an INSTANCE_HANDLE promised in prose outside it, or in a block that never
# closed, forwards nothing a consumer can act on.
_continuation_block() {
  printf '%s\n' "$1" | awk '
    /```[ \t]*continuation/ { incont=1; buf=""; next }
    incont && /```/         { incont=0; last=buf; have=1; next }
    incont                  { buf=buf $0 "\n" }
    END { if (have) printf "%s", last }' 2>/dev/null || true
}

# The raw `status:` value of a continuation block body (the first word after the LAST `status:`).
_continuation_status() {
  printf '%s\n' "$1" | awk '
    /status:/ { line=$0; sub(/.*status:[ \t]*/,"",line); sub(/[ \t].*/,"",line); last=line }
    END { print last }' 2>/dev/null || true
}

# A raw status reduced to a comparable KEY: uppercase, then only the leading [A-Z_] token, so a
# cosmetic spelling (`BLOCKED` in backticks, lower case, a trailing comma) compares equal. Empty
# key = no machine-readable status.
_continuation_status_key() {
  printf '%s' "$1" | tr 'a-z' 'A-Z' | sed -E 's/^[^A-Z_]*//; s/[^A-Z_].*$//' 2>/dev/null || true
}

# The handoff is PER LEASE. $1 = a continuation block body, $2 = lease tokens (newline-separated).
# Prints each token of $2 that the block forwards (the named-catcher handoff, T4), one per line:
# a `next:` entry that carries INSTANCE_HANDLE AND, after that key, the token itself. `next:` is
# the top-level key the driver turns into the catcher's brief, so it runs from its own line to the
# next top-level key; each entry starts at a `- ` item at the indent of the first one (a flow-style
# `next: [...]` on one line is one entry). A bare grep for INSTANCE_HANDLE anywhere in the fence was
# the defect this replaces: forwarding ONE lease's handle cleared EVERY live lease, and a
# token quoted in `blocked_reason` looked forwarded too.
_continuation_forwarded_tokens() {
  local block="$1" tokens="$2"
  [[ -n "$block" && -n "$tokens" ]] || return 0
  # Tokens travel into awk comma-joined: a newline inside a -v value is not portable awk.
  printf '%s\n' "$block" | awk -v toks="$(printf '%s\n' "$tokens" | paste -sd, -)" '
    BEGIN { nt = split(toks, T, ",") }
    function flush(   p, rest, i) {
      p = index(entry, "INSTANCE_HANDLE")
      if (p > 0) {
        rest = substr(entry, p)
        for (i = 1; i <= nt; i++) if (T[i] != "" && index(rest, T[i]) > 0) print T[i]
      }
      entry = ""
    }
    /^next:/ { innext = 1; ind = -1; entry = substr($0, 6); next }
    innext && /^[A-Za-z_][A-Za-z0-9_]*:/ { flush(); innext = 0; next }
    innext {
      if (match($0, /^[ \t]*-[ \t]/)) {
        if (ind < 0) ind = RLENGTH
        if (RLENGTH == ind) flush()
      }
      entry = entry "\n" $0
    }
    END { if (innext) flush() }' 2>/dev/null | sort -u || true
}

# The tokens of $2 (newline-separated) that the continuation block $1 does NOT forward - the leases
# still waiting for an owner. Prints nothing when every one of them is forwarded.
_continuation_unforwarded_tokens() {
  local block="$1" tokens="$2" fwd t
  fwd="$(_continuation_forwarded_tokens "$block" "$tokens")"
  while IFS= read -r t; do
    [[ -n "$t" ]] || continue
    printf '%s\n' "$fwd" | grep -qxF -- "$t" 2>/dev/null || printf '%s\n' "$t"
  done <<< "$tokens"
}

# rc 0 when this agent's report was already DELIVERED through SubagentHandback - the harness then
# refuses a second handback.
_handback_delivered() {
  local transcript="$1" n
  command -v jq >/dev/null 2>&1 || return 1
  [[ -n "$transcript" && -r "$transcript" ]] || return 1
  n="$(jq -rRs "$_FR_JQ_RECORDS$_FR_JQ_DELIVERED"' | $delivered | length' "$transcript" 2>/dev/null || true)"
  [[ "$n" =~ ^[0-9]+$ && "$n" -gt 0 ]]
}
