# transcript-lines.sh - SOURCED helper (not a hook): the ONE implementation of "the transcript lines
# that can hold a given kind of tool call and its result". A transcript grows to tens of MB; a hook
# that JSON-parses all of it to find a handful of calls outruns its timeout, and a gate the harness
# cancels decides nothing. final-report.sh and lease-correlation.sh read through it.
#
# _tool_call_lines <transcript> <key>...
#   Prints, in transcript order, every line that contains one of the fixed-string keys (a tool name,
#   a command fragment) plus every line that contains the tool_use id of a tool_use block found on
#   those lines - its tool_result, which need not repeat the key. A record can carry a tool call
#   whose name or input holds a key only if its raw line does, so a parser fed these lines sees
#   every such call and its result. Prints nothing when the transcript is unreadable or no key is
#   given.

_tool_call_lines() {
  local transcript="$1"; shift
  [[ -n "$transcript" && -r "$transcript" && $# -gt 0 ]] || return 0
  local keys ids
  keys="$(printf '%s\n' "$@")"
  ids=""
  if command -v jq >/dev/null 2>&1; then
    ids="$(grep -F -e "$keys" -- "$transcript" 2>/dev/null | jq -Rr --arg keys "$keys" '
      ($keys | split("\n") | map(select(length > 0))) as $k
      | fromjson? // empty | objects
      | ((.message // .).content // []) | (if type == "array" then .[] else empty end)
      | select(type == "object" and .type == "tool_use" and ((.id // "") | tostring) != "")
      | tojson as $j | select(any($k[]; . as $x | $j | contains($x)))
      | .id | tostring' 2>/dev/null | sort -u)"
  fi
  grep -F -e "$(printf '%s\n' "$keys" "$ids" | grep -v '^$')" -- "$transcript" 2>/dev/null || true
}
