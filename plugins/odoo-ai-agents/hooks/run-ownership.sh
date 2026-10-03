# run-ownership.sh - SOURCED helper (not a hook): the ONE implementation of "which of these run
# records is THIS session's run". The run-scoped advisories - remind-delegate.sh's mid-run nudge and
# drive-continuation.sh's unfinished-run reminder - ask it, so a NEEDS_NEXT run that another session
# (live or long dead) left in the same state dir never makes this session "mid-run".
#
# WHAT MAKES A RUN THIS SESSION'S: the session acted on it, and nobody has written it since.
#   - ACTED ON: an ASSISTANT tool call in this session's transcript names the run's file
#     (`run-<id>.json`) in its input - a Bash command (run-harness writes the record from a script),
#     a Read / Write / Edit file_path. That is how a run is driven: intake's Phase P writes it,
#     run-harness reads it at the top of every loop iteration and writes it after every node. A run
#     this session only SAW (a directory listing, a tool result, a hook message) was not acted on.
#   - NOBODY SINCE: the record's modification time is not later than this session's last call on
#     it (that call's result time). A later write came from another session that took the run over
#     - run-harness resuming it there - so it is that session's now, and this one's no longer.
# A RESUMED run is therefore this session's as soon as run-harness, resuming it here, reads its
# record - no field has to be stamped into the run record, and the record on disk is only read,
# never written.
#
# Fails SAFE to "not this session's run": no transcript, an unreadable one, no jq, a record this
# session never named. An advisory then stays silent; nothing is ever blocked on this answer.

# Seconds of slack between a record's mtime and the result time of the call that wrote it (the
# result record is written after the write; the slack only absorbs clock rounding).
_RUN_OWNER_SLACK=2

_run_file_mtime() {
  stat -c %Y -- "$1" 2>/dev/null || stat -f %m -- "$1" 2>/dev/null || true
}

# $1 = this session's transcript, $2.. = run record paths. Prints each record that is this
# session's run, one per line, in argument order.
_session_owned_runs() {
  local transcript="$1"; shift
  [[ $# -gt 0 && -n "$transcript" && -r "$transcript" ]] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  local -a names=()
  local rf
  for rf in "$@"; do names+=("${rf##*/}"); done
  # Only the lines naming one of the records can hold a call that acted on it; their tool_use ids
  # then find the result lines (which need not name the record).
  local calls
  calls="$(grep -F -e "$(printf '%s\n' "${names[@]}")" -- "$transcript" 2>/dev/null \
    | jq -Rr --args '
        fromjson? // empty | objects
        | def ts: (.timestamp // "") | tostring | sub("\\.[0-9]+"; "") | (fromdateiso8601? // 0);
        . as $r | ((.message // .) as $m | (($m.role // .type) // "")) as $role
        | select($role == "assistant") | ($r | ts) as $t
        | ((.message // .).content // []) | (if type == "array" then .[] else empty end)
        | select(type == "object" and .type == "tool_use")
        | (.input // {} | tojson) as $in | (.id // "") as $id
        | $ARGS.positional[] | select(. as $n | $in | contains($n))
        | [., $id, $t] | @tsv' "${names[@]}" 2>/dev/null)"
  [[ -n "$calls" ]] || return 0
  local ids results
  ids="$(printf '%s\n' "$calls" | cut -f2 | grep -v '^$' | sort -u)"
  results=""
  if [[ -n "$ids" ]]; then
    results="$(grep -F -e "$ids" -- "$transcript" 2>/dev/null \
      | jq -Rr '
          fromjson? // empty | objects
          | def ts: (.timestamp // "") | tostring | sub("\\.[0-9]+"; "") | (fromdateiso8601? // 0);
          . as $r | ((.message // .).content // []) | (if type == "array" then .[] else empty end)
          | select(type == "object" and .type == "tool_result")
          | [(.tool_use_id // ""), ($r | ts)] | @tsv' 2>/dev/null)"
  fi
  local name last mtime
  for rf in "$@"; do
    name="${rf##*/}"
    # The latest time this session acted on it: each call's result time, else the call's own.
    last="$(awk -F'\t' -v n="$name" '
      NR == FNR { if ($1 != "") rt[$1] = $2; next }
      $1 == n { t = ($2 in rt) ? rt[$2] : $3; if (t + 0 > best + 0) best = t }
      END { if (best != "") print best }' <(printf '%s\n' "$results") <(printf '%s\n' "$calls") 2>/dev/null)"
    [[ "$last" =~ ^[0-9]+$ && "$last" -gt 0 ]] || continue
    mtime="$(_run_file_mtime "$rf")"
    [[ "$mtime" =~ ^[0-9]+$ ]] || continue
    (( mtime <= last + _RUN_OWNER_SLACK )) && printf '%s\n' "$rf"
  done
  return 0
}
