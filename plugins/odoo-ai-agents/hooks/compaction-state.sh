# compaction-state.sh - SOURCED helper (not a hook): what a compaction must hand over to the next
# context window, and where it is kept. steer-compaction.sh (PreCompact) writes it,
# recover-after-compaction.sh (SessionStart, source compact) reads it; both build it through the
# same function, so the file and the transcript fallback agree.
#
# THE STATE is one JSON object:
#   {"skills": ["<plugin>:<skill>", ...],        plugin skills invoked this session, most recent last
#    "run": null | {"id","path","cursor","approach","skill"}}   the run this session owns, if any
# A skill is a plugin skill when its invocable name carries the odoo-ai-agents: or git-toolkit:
# prefix. The run is the one hooks/run-ownership.sh attributes to this session among the records in
# the project's state dir whose status is NEEDS_NEXT or RUNNING; when ownership cannot be told, no
# run is named (a wrong run is worse than none). run.skill is the skill of the run's cursor node
# when that node's approach_kind is skill, else empty.
#
# THE FILE lives at <state root>/compaction/<session id>.json (state root: odoo_ai_state_root of
# scripts/lib/state_reclaim.sh). Writes are atomic (temp file + mv); files older than seven days
# are removed on each write. Everything here needs jq and fails soft: no jq, no state root or an
# unreadable transcript gives an empty result, never an error.

_CS_HOOK_DIR="${BASH_SOURCE[0]%/*}"
_CS_MAX_OTHER_SKILLS=12

# The compaction state directory, or nothing when the state root cannot be resolved.
_cs_dir() {
  local lib="${CLAUDE_PLUGIN_ROOT:-${_CS_HOOK_DIR}/..}/scripts/lib/state_reclaim.sh" root
  [[ -r "$lib" ]] || return 0
  # shellcheck source=/dev/null
  . "$lib" 2>/dev/null || return 0
  command -v odoo_ai_state_root >/dev/null 2>&1 || return 0
  root="$(odoo_ai_state_root 2>/dev/null)" || return 0
  [[ -n "$root" ]] && printf '%s\n' "$root/compaction"
  return 0
}

# $1 = session id. Prints the state file path, or nothing for an unusable id or root.
_cs_file() {
  [[ "${1:-}" =~ ^[A-Za-z0-9_-]+$ ]] || return 0
  local dir
  dir="$(_cs_dir)"
  [[ -n "$dir" ]] && printf '%s/%s.json\n' "$dir" "$1"
  return 0
}

# $1 = transcript. Prints the plugin skills invoked in it, one per line, each once, most recent
# last. A fixed-string prefilter keeps jq off the lines that cannot hold an invocation.
_cs_skills() {
  [[ -n "${1:-}" && -r "$1" ]] || return 0
  { grep -F -e '"Skill"' -e 'command-name' -- "$1" 2>/dev/null || true; } \
    | jq -Rr '
        def names:
          if type == "string" then (scan("<command-name>/?([^<\\s]+)</command-name>") | .[0])
          elif type == "object" then
            (if .type == "tool_use" and .name == "Skill" then (.input.skill // empty | strings)
             elif .type == "text" then (.text // "" | names)
             else empty end)
          else empty end;
        fromjson? | objects | ((.message // .).content // empty)
        | (if type == "array" then .[] else . end) | names' 2>/dev/null \
    | grep -E '^(odoo-ai-agents|git-toolkit):[A-Za-z0-9_-]+$' \
    | awk '{ l[NR] = $0; last[$0] = NR } END { for (i = 1; i <= NR; i++) if (last[l[i]] == i) print l[i] }'
  return 0
}

# $1 = transcript, $2 = project cwd. Prints the run object this session owns, or `null`.
_cs_run() {
  local transcript="${1:-}" cwd="${2:-}" dir rf owned rc
  [[ -r "${_CS_HOOK_DIR}/run-ownership.sh" ]] || { echo null; return 0; }
  # shellcheck source=/dev/null
  . "${_CS_HOOK_DIR}/run-ownership.sh"
  dir="$(_run_state_dir "$cwd")"
  local -a live=()
  if [[ -d "$dir" ]]; then
    for rf in "$dir"/run-*.json; do
      [[ -f "$rf" ]] || continue
      case "$(jq -r '.status // empty' "$rf" 2>/dev/null || true)" in
        NEEDS_NEXT|RUNNING) live+=("$rf") ;;
      esac
    done
  fi
  [[ ${#live[@]} -gt 0 ]] || { echo null; return 0; }
  owned="$(_session_owned_runs "$transcript" "${live[@]}")"; rc=$?
  { (( rc == 0 )) && [[ -n "$owned" ]]; } || { echo null; return 0; }
  rf="${owned%%$'\n'*}"
  local id="${rf##*/run-}"; id="${id%.json}"
  jq -c --arg path "$rf" --arg fid "$id" '
    (.cursor // "") as $c
    | ([.nodes[]? | objects | select((.id // "") == $c)][0] // {}) as $n
    | ($n.approach // "" | tostring | gsub("\\s+"; " ") | .[0:80]) as $ap
    | {id: (.run_id // $fid), path: $path, cursor: $c, approach: $ap,
       skill: (if ($n.approach_kind // "") == "skill" and $ap != ""
               then (if ($ap | contains(":")) then $ap else "odoo-ai-agents:" + $ap end)
               else "" end)}' "$rf" 2>/dev/null || echo null
  return 0
}

# $1 = transcript, $2 = project cwd. Prints the state object; `{"skills":[],"run":null}` when
# nothing can be read.
_cs_build_state() {
  command -v jq >/dev/null 2>&1 || { echo '{"skills":[],"run":null}'; return 0; }
  local skills run
  skills="$(_cs_skills "${1:-}" | jq -Rsc 'split("\n") | map(select(length > 0))' 2>/dev/null)"
  run="$(_cs_run "${1:-}" "${2:-}")"
  jq -cn --argjson s "${skills:-[]}" --argjson r "${run:-null}" '{skills: $s, run: $r}' 2>/dev/null \
    || echo '{"skills":[],"run":null}'
  return 0
}

# $1 = state file, $2 = state object. Writes atomically; silent on any failure.
_cs_write() {
  local file="$1" state="$2" dir tmp
  dir="${file%/*}"
  mkdir -p "$dir" 2>/dev/null || return 0
  find "$dir" -maxdepth 1 -name '*.json' -mtime +7 -delete 2>/dev/null || true
  tmp="$(mktemp "$dir/.state.XXXXXX" 2>/dev/null)" || return 0
  if printf '%s\n' "$state" >"$tmp" 2>/dev/null && mv -f "$tmp" "$file" 2>/dev/null; then
    return 0
  fi
  rm -f "$tmp" 2>/dev/null
  return 0
}

# $1 = state file. Prints its object when it is a JSON object, else nothing.
_cs_read() {
  [[ -n "${1:-}" && -r "$1" ]] || return 0
  jq -ce 'select(type == "object")' "$1" 2>/dev/null || true
  return 0
}
