# run-ownership.sh - SOURCED helper (not a hook): the ONE implementation of "where are this project's
# run records, which of them are NEEDS_NEXT, and which of those is THIS session's run". The
# run-scoped advisories - remind-delegate.sh's mid-run nudge and drive-continuation.sh's
# unfinished-run reminder - read it (parse-continuation.sh reads only the state dir), so a NEEDS_NEXT
# run that another session (live or long dead) left in the same state dir never makes this session
# "mid-run".
#
# WHAT MAKES A RUN THIS SESSION'S: the LAST write to its record came from this session. A record is
# written by a tool call that names it - intake's Phase P creates it, run-harness writes it after
# every node and before every dispatch, from a script or the Write/Edit tools - so the record's
# modification time falls inside the run time of one of this session's calls naming it (from the
# call record's time to its result record's time). Reading a record (intake's active-run check,
# a status look) writes nothing and so makes nothing this session's. A later write by another
# session - run-harness resuming the run there - moves the record's time outside every window of
# this session: the run is that session's now. A RESUMED run becomes this session's at run-harness's
# first write here (it persists RUNNING before it dispatches anything). Run records are only read.
#
# THREE ANSWERS, never a guess: _session_owned_runs returns 0 with this session's runs (none is a
# real answer: another session's run, or an old record no session here wrote); it returns 2 when it
# cannot tell - no transcript, an unreadable one, a jq that cannot run the scan. A caller keeps the
# behaviour it had before ownership existed for "cannot tell", and never blocks on any answer.

# Seconds of slack around a call's run window: timestamps are compared in whole seconds.
_RUN_OWNER_SLACK=2

_run_file_mtime() {
  stat -c %Y -- "$1" 2>/dev/null || stat -f %m -- "$1" 2>/dev/null || true
}

# The ISOLATE state dir holding this project's run records, resolved FROM the hook's own project cwd
# ($1, else $CLAUDE_PROJECT_DIR, else .) per snippets/state-root-resolution.md. When the resolver
# refuses (non-git, no marker) or cannot run (no CLAUDE_PLUGIN_ROOT) it falls back to the legacy
# <proj>/.odoo-ai - the sanctioned "Advisory-glob exception" of that snippet: callers only glob it,
# read-only, and a wrong location matches nothing. Never copy this fallback into a call site that
# writes.
_run_state_dir() {
  local proj="${1:-${CLAUDE_PROJECT_DIR:-.}}" dir
  dir="$(cd "$proj" 2>/dev/null && bash "${CLAUDE_PLUGIN_ROOT:-}/scripts/lib/resolve_project_dir.sh" isolate 2>/dev/null || true)"
  printf '%s\n' "${dir:-${proj}/.odoo-ai}"
}

# The run records in state dir $1 whose status is NEEDS_NEXT, one path per line.
_needs_next_runs() {
  local rf
  [[ -d "${1:-}" ]] || return 0
  for rf in "$1"/run-*.json; do
    [[ -f "$rf" ]] || continue
    [[ "$(jq -r '.status // empty' "$rf" 2>/dev/null || true)" == "NEEDS_NEXT" ]] && printf '%s\n' "$rf"
  done
  return 0
}

# $1 = this session's transcript, $2.. = run record paths. Prints each record that is this session's
# run, newest write first, one per line. Returns 0 when it could tell (even with nothing printed), 2
# when it could not.
_session_owned_runs() {
  local transcript="$1"; shift
  [[ $# -gt 0 ]] || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || return 2
  command -v jq >/dev/null 2>&1 || return 2
  local -a names=()
  local rf
  for rf in "$@"; do names+=("${rf##*/}"); done
  local list rc calls results ids
  list="$(printf '%s\n' "${names[@]}")"
  # Only the lines naming a record can hold a call that wrote it; their tool_use ids then find the
  # result lines (which need not name the record). One "<name>\t<id>\t<call time>" row per call.
  calls="$({ grep -F -e "$list" -- "$transcript" 2>/dev/null || true; } \
    | jq -Rr --arg names "$list" '
        def ts: (.timestamp // "") | tostring | sub("\\.[0-9]+"; "") | (fromdateiso8601? // 0);
        ($names | split("\n") | map(select(length > 0))) as $ns
        | fromjson? // empty | objects
        | . as $r | (((.message // .).role // .type) // "") as $role
        | select($role == "assistant") | ($r | ts) as $t
        | ((.message // .).content // []) | (if type == "array" then .[] else empty end)
        | select(type == "object" and .type == "tool_use")
        | (.input // {} | tojson) as $in | (.id // "" | tostring) as $id
        | $ns[] | select(. as $n | $in | contains($n))
        | [., $id, ($t | tostring)] | @tsv')"
  rc=$?
  (( rc == 0 )) || return 2
  results=""
  ids="$(printf '%s\n' "$calls" | cut -f2 | grep -v '^$' | sort -u)"
  if [[ -n "$ids" ]]; then
    results="$({ grep -F -e "$ids" -- "$transcript" 2>/dev/null || true; } \
      | jq -Rr '
          def ts: (.timestamp // "") | tostring | sub("\\.[0-9]+"; "") | (fromdateiso8601? // 0);
          fromjson? // empty | objects
          | . as $r | ((.message // .).content // []) | (if type == "array" then .[] else empty end)
          | select(type == "object" and .type == "tool_result")
          | [(.tool_use_id // "" | tostring), ($r | ts | tostring)] | @tsv')" || return 2
  fi
  local name mtime
  for rf in "$@"; do
    name="${rf##*/}"
    mtime="$(_run_file_mtime "$rf")"
    [[ "$mtime" =~ ^[0-9]+$ ]] || continue
    # Did one of this session's calls naming the record run while it was last written?
    awk -F'\t' -v n="$name" -v m="$mtime" -v s="$_RUN_OWNER_SLACK" '
      NR == FNR { if ($1 != "") rt[$1] = $2; next }
      $1 == n && $3 > 0 {
        end = ($2 in rt) ? rt[$2] : $3
        if (m + 0 >= $3 - s && m + 0 <= end + s) { found = 1 }
      }
      END { exit(found ? 0 : 1) }' <(printf '%s\n' "$results") <(printf '%s\n' "$calls") 2>/dev/null \
      && printf '%s\t%s\n' "$mtime" "$rf"
  done | sort -rn -k1,1 | cut -f2-
  return 0
}
