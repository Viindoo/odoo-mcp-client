#!/usr/bin/env bash
# block-unowned-lease-mutation.sh - PreToolUse HARD DENY. The enforcement half of the allocator's
# ownership guard (${CLAUDE_PLUGIN_ROOT}/docs/reference/INSTANCE-ALLOCATION-GUARDS.md section 6.3) and of
# ${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md T1 ("teardown belongs to whoever
# ACQUIRED the resource").
#
# THE INCIDENT IT EXISTS FOR: a dispatched agent given a purely documentary brief - no instance, no
# lease token handed to it, no execution asked for - ended its turn by running
# `allocator.py release <token>` on a live acceptance lease belonging to the run that had dispatched
# it. `drop_on_release: true` fired and a freshly built database was destroyed. Its stated reasoning
# was that the lease "looked orphaned"; the question it never asked was DID I ACQUIRE THIS. The
# agent's own definition called it read-only and a HARD LEAF - but that prohibition was PROSE, with
# no gate under it, exactly like the coordinator-authoring breach that
# hooks/block-coordinator-code-write.sh was written for.
#
# WHAT IT REFUSES - four arms, all scoped to a SUBAGENT caller:
#   A1  `allocator.py release ...`, `allocator.py park ...` or `allocator.py adopt ...` in a command
#       segment that names NO `--run-id` (nor its `--session` alias). A release must NAME the run
#       that owns the lease; an absent run id is not "the owner forgot a flag", it is ownership not
#       established. `park` stops the same server process group under the allocator's same
#       ownership rule (`_ownership_refusal`), so it carries the same proof. `adopt`
#       re-anchors a lease onto the caller's session - it moves who vouches for a live instance, so
#       it carries the same proof. A rightful owner always has the value - `ALLOC_RUN_ID` from its
#       own acquire, `INSTANCE_HANDLE.run_id` downstream - so this arm costs a legitimate call
#       nothing and refuses the incident's exact shape.
#   A2  `--force` / `--force-forget` on `release`, `--force` on `park`, `--yes` on `reap-orphans`,
#       or `--allow-unowned`
#       on `acquire`, from a subagent.
#       The allocator's own refusal names `--force` as the override, so without this arm a
#       dispatched agent that reads that refusal is ONE FLAG away from the same data loss, by the
#       same "it looked orphaned" reasoning. `--force` overrides a human's ownership decision; it is
#       a human's call, and a dispatched agent's route is to report the refusal upward instead.
#   A3  `allocator.py gc` WITHOUT `--dry-run`, from a subagent. The registry is MACHINE-GLOBAL -
#       every session on this host shares it - and an applying gc stops process groups and DROPS
#       databases across all of them (`--scope all` includes the TTL arm; `--scope anchor --force`
#       overrides a live session's protection). That is a janitor's call made with the whole host
#       in view, never a dispatch's side effect; the only automatic applier is the SessionEnd hook,
#       which is not a subagent. `gc --dry-run` changes nothing and always passes.
#   A4  a release, park or adopt of a lease this subagent does NOT hold - through Bash
#       (`allocator.py release|park|adopt <tok> ...`) OR the odoo-local MCP tools `lease_release` /
#       `lease_park` / `lease_adopt` (argument `lease_token`, the name the tools require; a stray
#       `token` key is read as well so a mis-spelled call is still judged, not waved through). An
#       adopt is also allowed for a token the agent's OWN `lease_find` result returned - the
#       legitimate resume path, lease_find(parked, run_id) -> lease_adopt -> instance_serve. The
#       adopt is the explicit take-over: once it succeeds the token counts as OBTAINED, so the
#       resumer's later park or release passes here and the teardown gate holds it to one of them.
#       Finding alone is never enough for a release or park. The owner-naming arm A1 cannot catch this: ownership is
#       RUN-scoped, and an INSTANCE_HANDLE forwarded DOWN to a consumer carries the provider's
#       run_id, so a consumer that copies it into `--run-id` / `run_id` names a real owner and the
#       allocator ACCEPTS the call - destroying the instance its provider still uses. The contract
#       (resource-teardown-contract.md T1) is narrower than the run: release or park only a lease
#       you OBTAINED yourself, or one provisioned for your run and handed back UP to you by a child
#       you dispatched; a handle forwarded DOWN is never yours. So the target token must appear in
#       the calling agent's OWN transcript as (a) obtained - hooks/lease-correlation.sh
#       `_lease_owned_tokens`, the SAME implementation enforce-teardown.sh uses, so every lease
#       that gate orders released passes here - or (b) handed up - inside the returned report of
#       one of its own Agent/Task calls (`_lease_handed_up_text`). Anything else is refused, and a
#       token its brief forwarded is refused with the words that say so. The transcript is
#       `agent_transcript_path`, else the harness's `<session>/subagents/agent-<agent_id>.jsonl`
#       layout; if neither is readable the arm FAILS OPEN (logged to stderr) - uncertainty is never
#       a deny here. A Bash token that is not a literal (`"$TOK"`, `${ALLOC_TOKEN}`) cannot be
#       compared and passes this arm (arm A1 still applies to it).
#
# WHY IDENTITY-FREE (no per-agent allow-list): the agent-role SSOT
# (generator/skill_tool_deps.json `.agents.<name>.role`) has exactly two live values here, `leaf`
# and `coordinator`, and the agents that legitimately drive the allocator (`odoo-instance-ops`,
# `odoo-qa-tester`, `odoo-coder`) sit on BOTH sides of that line - so `role` cannot separate "may
# mutate a lease" from "may not", and a new per-agent classification would be 26 hand-made
# judgements, each one an outage on the pipeline it mis-marks. This gate instead asserts the ONE
# property every legitimate caller can satisfy and the incident's caller could not: name the owner.
# It therefore also covers agents that do not exist yet.
#
# WHY A SUBAGENT ONLY: the ROOT is never denied (the same rule remind-delegate.sh and
# block-coordinator-code-write.sh follow). A human is present in the main context to read the
# allocator's own refusal and decide; a dispatched agent is not, and the incident happened in a
# dispatch. The allocator refuses a foreign or un-named release for EVERY caller regardless - this
# hook is the earlier, explanatory layer, and the layer that still holds if the allocator predicate
# is ever loosened again.
#
# EXECUTION POSITION, NOT A MENTION. Position is decided by walking from the START of the segment:
# leading `VAR=value` assignments, exec wrappers (`eval` among them) and their options are skipped,
# and the first REAL command word must then be the script itself or a python interpreter whose
# first token after its own options (`-u`, `-I`, `-X dev`, ...) is the script. The body of every command substitution - `$(...)` and backticks, even
# inside double quotes, never inside single quotes - is ALSO a segment: the shell EXECUTES it, so
# `eval "$(python3 .../allocator.py acquire --allow-unowned ...)"`, the allocator's own documented
# acquire shape, is an invocation of `acquire`, not a mention of it. A read-only reference - `grep -rn 'allocator.py release' scripts/`, `sed -n
# '/allocator.py release/p'`, an echoed remediation line, a `python3 -c` string, a worklog entry
# quoting any of them - is therefore never mistaken for a call. This rule was added after this
# gate's own test caught the first detector DENYING a plain `grep`: a guard that blocks reading the
# code it guards is an outage, not a safeguard, and it would have blocked the very investigation
# that diagnoses an incident. It was TIGHTENED after the same thing happened again: the test was
# ADJACENCY - `allocator.py` preceded by a python token anywhere in the segment - so the moment a
# quoted sentence spelled the interpreter too (`echo "then run: python3 .../allocator.py release
# $TOK"`), the mention read as an invocation and this gate refused an agent for DESCRIBING a
# command, twice, during an investigation of its own sibling. The verb is read as the NEXT token
# after the script, so a verb spelled inside a quoted pattern can never stand in for one on a
# command line.
#
# WHAT THE ARMS ARE RUN OVER: hooks/command-segments.sh, the segmentation SSOT this gate shares
# with block-coordinator-code-write.sh. Continuations are joined BEFORE splitting, which closes a
# hole that ran in both directions at once: `release <tok> \` + `--run-id <id>` used to refuse a
# lease the caller genuinely owned, while `--run-id <id> \` + `--force` used to slip an override
# past arm A2 entirely, because the override sat in a segment carrying no allocator token.
#
# WHAT IT PROVABLY DOES NOT CATCH - stated, not papered over:
#   - `resume`, `heartbeat` and `bind` on a lease the caller does not own. Those verbs accept no
#     `--run-id`, so there is nothing to require. Refusing an un-named `park` cannot deadlock a
#     subagent at the SubagentStop teardown gate: the rightful owner holds its run id, and the third
#     exit - forwarding INSTANCE_HANDLE - needs no tool call at all.
#   - a run id that is present but WRONG or empty (`--run-id ""`, `--run-id $UNSET`): this arm is
#     lexical. The allocator's own comparison under flock is what catches those.
#   - a command whose verb or flags are COMPUTED (`$VERB`, `"$FLAGS"`), assembled inside a script
#     the command only invokes (`bash teardown.sh`), or backgrounded outside the Bash tool.
#   - an invocation whose interpreter is not spelled literally (`"$PY" .../allocator.py release`):
#     the execution-position test needs a `python`-shaped token before the script path, and an
#     unresolvable one reads as "cannot classify" -> pass, per this file's fail-open rule.
#   - a release issued through some tool other than Bash or the odoo-local lease_release /
#     lease_park tools, or from the root context.
#   - arm A4 with a token that is not a literal, or with no readable agent transcript.
#   - arm A4 trusts a successful EARLIER adopt as ownership: it refuses the adopt of a forwarded
#     token, but an adopt the gate did not see (a non-literal Bash token) still counts afterwards.
#   - a separator inside quotes still splits the segment (`--reason "a && b"`): segmentation is
#     lexical, not a shell parse.
#   - a body fed to an interpreter heredoc (`bash <<EOF ... EOF`) is kept as text so the detectors
#     still see it, but it is not parsed as the script it is. A DATA heredoc's body (`cat >> log.md
#     <<EOF`) is dropped before matching, which is what makes writing a worklog that NAMES this
#     command no longer read as running it.
#   - `reap-orphans` without `--yes` and `gc --dry-run`: both only LIST. They are deliberately not
#     refused - a dispatch reporting what a janitor WOULD reclaim is exactly the upward report the
#     refusals below ask for.
#   - a HELP invocation (`allocator.py release --help`, `park -h`, `gc --help`): the allocator prints
#     usage and exits before it reads anything else on the line (`main()` checks `-h`/`--help`
#     anywhere in the verb's own arguments), so it mutates nothing and passes every arm. Only a bare
#     `-h`/`--help` word counts - one inside a quoted value (`--reason "see --help"`) reaches the
#     allocator as part of that value, so it never buys a pass.
#   - a command substitution nested inside another one is unwrapped (`$(... $(...) ...)`), but a
#     substitution inside a DATA heredoc body is not - that body is dropped before matching (see
#     command-segments.sh), even though an unquoted heredoc delimiter would expand it.
#
# FAILS OPEN ON EVERY UNCERTAINTY (the _pass convention this plugin's hooks share): no jq, empty or
# unparseable stdin, a tool outside the matcher, a command that never names `allocator.py`, or a
# caller that is not identifiably a subagent -> silent pass, exit 0.
#
# SCHEMA: PreToolUse's documented shape - hookSpecificOutput.permissionDecision = "deny" with a
# permissionDecisionReason. Exit code is ALWAYS 0; a PreToolUse hook that hard-fails is an outage.

set -uo pipefail
_pass() { exit 0; }

# Segmentation SSOT: hooks/command-segments.sh, resolved relative to THIS script so the gate gains
# no dependency on $CLAUDE_PLUGIN_ROOT. Unreadable or truncated -> fail open, the convention every
# hook in this plugin follows.
_CMDSEG_LIB="${BASH_SOURCE[0]%/*}/command-segments.sh"
if [[ -r "$_CMDSEG_LIB" ]]; then
  # shellcheck source=/dev/null
  . "$_CMDSEG_LIB"
else
  _pass
fi
declare -F _logical_segments >/dev/null 2>&1 || _pass

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass
printf '%s' "$INPUT" | jq -e . >/dev/null 2>&1 || _pass

TOOL="$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)"
MCP_VERB=""
if [[ "$TOOL" =~ odoo-local__lease_(release|park|adopt)$ ]]; then
  MCP_VERB="${BASH_REMATCH[1]}"
elif [[ "$TOOL" != "Bash" ]]; then
  _pass
fi

# Caller must be a subagent - ANY populated agent_id/agent_type. Same identity signal, same V-52
# rule, as hooks/remind-delegate.sh and hooks/block-coordinator-code-write.sh. The ROOT is never
# denied.
AGENT_ID="$(printf '%s' "$INPUT" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
AGENT_TYPE="$(printf '%s' "$INPUT" | jq -r '.agent_type // .agentType // empty' 2>/dev/null || true)"
[[ -n "$AGENT_ID" || -n "$AGENT_TYPE" ]] || _pass

AGENT_NAME="${AGENT_TYPE##*:}"
[[ -n "$AGENT_NAME" ]] || AGENT_NAME="this subagent"

# --- Arm A4: release/park only a lease this agent holds (see header) --------------------------
# Correlation SSOT: hooks/lease-correlation.sh, shared with enforce-teardown.sh. Unreadable ->
# arm A4 is simply not run (fail open), the convention for every hook in this plugin.
_LEASE_LIB="${BASH_SOURCE[0]%/*}/lease-correlation.sh"
if [[ -r "$_LEASE_LIB" ]]; then
  # shellcheck source=/dev/null
  . "$_LEASE_LIB"
fi

# Prints the A4 refusal for $1 = verb label, $2 = token, $3 = release|park|adopt, or nothing when
# the token is held (or when holding cannot be judged). An ADOPT is also allowed for a token this
# agent found itself through its own lease_find result - the resume-in-a-new-session path
# (lease_find(parked, run_id) -> lease_adopt). Finding is never enough for a release or park.
_a4_reason() {
  local verb="$1" tok="$2" kind="$3" tr
  [[ "$tok" =~ ^[A-Za-z0-9_-]{8,}$ ]] || return 0          # not a literal token: cannot compare
  declare -F _lease_owned_tokens >/dev/null 2>&1 || return 0
  tr="$(_lease_agent_transcript "$INPUT")"
  if [[ -z "$tr" ]]; then
    echo "block-unowned-lease-mutation: no readable agent transcript; lease-ownership arm skipped (fail open)" >&2
    return 0
  fi
  _lease_owned_tokens "$tr" | grep -qxF -- "$tok" && return 0
  _lease_handed_up_text "$tr" | grep -qF -- "$tok" && return 0
  if [[ "$kind" == "adopt" ]]; then
    _lease_found_text "$tr" | grep -qF -- "$tok" && return 0
  fi
  local how
  if [[ "$kind" != "adopt" ]] && _lease_found_text "$tr" | grep -qF -- "$tok"; then
    how="your own lease_find returned this parked lease, and finding it is not holding it. To resume it, TAKE IT OVER first: lease_adopt {lease_token, run_id} (the explicit take-over), then instance_serve {lease_token} to bring it back. After the adopt it is yours - this $verb then passes, and the teardown gate holds you to releasing, parking or handing it off before your terminal status."
  elif _lease_brief_text "$tr" | grep -qF -- "$tok"; then
    how="this lease was forwarded to you - it arrived in your brief or a message from your caller, so you are its CONSUMER. Leave it for the agent that provisioned it; if you are done with it, hand it back UP in your continuation instead (forward INSTANCE_HANDLE in next.inputs to your caller)."
  else
    how="nothing in your own transcript shows you obtaining this lease - no lease_acquire / lease_adopt result, no series-mode instance_serve that LAUNCHED its server (attaching to a server another run started is not obtaining it), no Bash allocator acquire receipt - and no child you dispatched handed it back up to you. Holding or finding a token (lease_list, lease_find, a log) is not ownership. Leave it alone and report it in your terminal status for its owner or the allocator's gc."
    [[ "$kind" == "adopt" ]] && how="nothing in your own transcript shows you obtaining this lease, no child you dispatched handed it back up to you, and your own lease_find never returned it. To resume a parked lease of YOUR run from a new session, call lease_find (state parked, your run_id) first, lease_adopt the token IT returns, then instance_serve it; a token from a listing, a log or anywhere else is not yours to take over."
  fi
  printf '%s' "REFUSED: you are \`$AGENT_NAME\`, and this $verb targets lease $tok, which is not yours to $verb: $how

Ownership is RUN-scoped in the allocator, so copying the run_id of a handle you were GIVEN would make this call succeed - and destroy (release), stop (park) or take over (adopt) an instance the agent that provisioned it is still using. The rule is narrower than the run (snippets/resource-teardown-contract.md T1): release, park or adopt only a lease you obtained yourself, or one provisioned for your run and handed back UP to you by a child you dispatched (an adopt may also take a parked lease of your run that your OWN lease_find returned). A handle forwarded DOWN is never yours.

Serving or resuming a forwarded handle (instance_serve with its lease_token) is consumption, not obtainment, so the teardown gate never asks you to release it: at your turn end it needs nothing from you for a lease you only consumed. Re-sending this call in a different shape to get past the guard is itself a blocked action; if you believe the lease IS yours, end your turn BLOCKED and quote this refusal."
}

_deny() {
  jq -cn --arg reason "$1" \
    '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$reason}}'
  exit 0
}

if [[ -n "$MCP_VERB" ]]; then
  MCP_TOK="$(printf '%s' "$INPUT" | jq -r '.tool_input.lease_token // .tool_input.token // empty | strings' 2>/dev/null || true)"
  [[ -n "$MCP_TOK" ]] || _pass
  R="$(_a4_reason "lease_$MCP_VERB" "$MCP_TOK" "$MCP_VERB")"
  [[ -n "$R" ]] && _deny "$R"
  _pass
fi

CMD="$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
[[ -n "$CMD" ]] || _pass
printf '%s' "$CMD" | grep -q 'allocator\.py' || _pass

# The allocator verb this segment RUNS, or nothing. Pure bash token walk - no awk, no second
# quoting layer to get wrong.
#
# EXECUTION POSITION is decided by walking from the START of the segment, never by looking at
# whatever token happens to sit before `allocator.py`. Adjacency alone was the old test, and it
# made any sentence that QUOTED an invocation read as one: `echo "then run: python3
# .../allocator.py release $TOK"` and a worklog line carrying the same sentence were both refused.
# A gate that refuses an agent for DESCRIBING a command is an outage - it blocked this gate's own
# incident investigation twice - and the header's "a mention is never an invocation" promise was
# false for exactly that shape. So: skip leading `VAR=value` assignments, exec wrappers and their
# options, then require the first REAL command word to be the script itself or a python
# interpreter whose first token after its own options is the script.
_alloc_verb() {
  local -a toks=()
  read -r -a toks <<< "$1"
  local n=${#toks[@]} i=0 cur
  while (( i < n )); do
    cur="${toks[i]//[\"\']/}"
    case "$cur" in
      # env-assignment prefix, an option, or a wrapper's numeric argument (`timeout 30 ...`)
      [A-Za-z_]*=*|-*|[0-9]*) (( i++ )); continue ;;
      # exec wrappers: the real command word is further right. `bash`/`sh` are here so
      # `bash -c "python3 .../allocator.py release tok"` stays caught, while `bash teardown.sh`
      # lands on a script this gate cannot read and passes - a residual the header already names.
      command|exec|eval|nohup|time|timeout|sudo|nice|stdbuf|env|bash|sh|zsh|ksh|dash) (( i++ )); continue ;;
    esac
    break
  done
  (( i < n )) || return 0
  cur="${toks[i]//[\"\']/}"
  # the script invoked directly: ./scripts/lib/allocator.py <verb> ...
  if [[ "$cur" == *allocator.py ]]; then
    (( i + 1 < n )) || return 0          # nothing after the script path: no verb
    printf '%s\n' "${toks[i+1]//[\"\']/}"
    return 0
  fi
  # a python interpreter running it: the script must be the first token after the INTERPRETER'S
  # OWN OPTIONS. Those options change how python runs, not what it runs, so `python3 -u
  # .../allocator.py release <tok>` (or -I, -O, -B, -E, -s, -X dev, -W error, a cluster like -uB)
  # is exactly as much an invocation as the bare form - requiring the script at i+1 let every one of
  # them walk past all four arms. -X and -W take a value (attached, `-Xdev`, or the next word); -c
  # and -m end the option list with code or a module to run INSTEAD of a script, so the segment is
  # not running allocator.py and is left alone; `--` ends the options. Anything else starting with
  # `-` is a valueless flag (python's long options besides --check-hash-based-pycs take none).
  case "$cur" in
    python|python[0-9]*|*/python|*/python[0-9]*) ;;
    *) return 0 ;;                       # a MENTION, not an invocation
  esac
  (( i++ ))
  local opt k ch
  while (( i < n )); do
    opt="${toks[i]//[\"\']/}"
    case "$opt" in
      --) (( i++ )); break ;;
      --check-hash-based-pycs) (( i += 2 )); continue ;;
      --*) (( i++ )); continue ;;
      -?*) ;;
      *) break ;;
    esac
    # a short-option cluster: walk it one letter at a time
    (( i++ ))
    for (( k = 1; k < ${#opt}; k++ )); do
      ch="${opt:k:1}"
      case "$ch" in
        c|m) return 0 ;;                 # code / module instead of a script: not this script
        X|W) (( k + 1 < ${#opt} )) || (( i++ )); break ;;   # value attached, or the next word
      esac
    done
  done
  (( i + 1 < n )) || return 0
  [[ "${toks[i]//[\"\']/}" == *allocator.py ]] || return 0
  printf '%s\n' "${toks[i+1]//[\"\']/}"
}

# The positional token of the allocator verb this segment RUNS ("" when there is none). Same walk as
# _alloc_verb to the verb, then the allocator's own argv rule (allocator.py `_parse`): a boolean
# flag takes no value, `--flag=value` is one word, any other `--flag` takes the next word, and the
# first remaining word is the token. The boolean set mirrors allocator.py `_BOOL_KEYS`.
_alloc_token() {
  local -a toks=()
  read -r -a toks <<< "$1"
  local n=${#toks[@]} i=0 cur
  while (( i < n )); do
    cur="${toks[i]//[\"\']/}"
    (( i++ ))
    [[ "$cur" == *allocator.py ]] && break
  done
  (( i < n )) || return 0
  (( i++ ))                                  # the verb
  while (( i < n )); do
    cur="${toks[i]//[\"\']/}"
    case "$cur" in
      --no-create|--force|--show-tokens|--yes|--force-forget|--force-attach|--allow-unowned|--dry-run|--with-verdict|--print|--help) (( i++ )) ;;
      --*=*) (( i++ )) ;;
      --*) (( i += 2 )) ;;
      *) printf '%s\n' "$cur"; return 0 ;;
    esac
  done
}

# One LOGICAL simple command per line, so a flag can never be borrowed from a NEIGHBOURING command
# (`allocator.py release $T && echo --run-id`) AND a command written across two physical lines with
# a trailing `\` stays the one command it is. Both directions matter here: the split form used to
# refuse a release whose `--run-id` sat on the continuation line, and to let a `--force` on the
# continuation line past the override arm entirely. Segmentation is the shared SSOT in
# hooks/command-segments.sh - never re-implement it here.
# The body of every command substitution in $1 - `$(...)` and `...` - outside single quotes,
# one body per line (inner newlines flattened; the caller re-segments each body). A pure bash
# character walk: `$(` is active inside double quotes and inert inside single quotes, exactly as
# the shell treats it; the matching `)` is found by depth, skipping quoted parentheses. `$((`
# arithmetic yields a harmless body. Unbalanced input stops the walk (fail open on the rest).
_cmd_substitutions() {
  local s="$1" n=${#1} i=0 c dq=0 j depth q body
  while (( i < n )); do
    c="${s:i:1}"
    if [[ "$c" == "\\" ]]; then (( i += 2 )); continue; fi
    if (( ! dq )) && [[ "$c" == "'" ]]; then
      j=$(( i + 1 ))
      while (( j < n )) && [[ "${s:j:1}" != "'" ]]; do (( j++ )); done
      (( i = j + 1 )); continue
    fi
    if [[ "$c" == '"' ]]; then (( dq = !dq, i++ )); continue; fi
    if [[ "$c" == '$' && "${s:i+1:1}" == '(' ]]; then
      j=$(( i + 2 )); depth=1; q=""
      while (( j < n && depth > 0 )); do
        c="${s:j:1}"
        if [[ -n "$q" ]]; then
          [[ "$c" == "\\" && "$q" == '"' ]] && (( j++ ))
          [[ "$c" == "$q" ]] && q=""
        elif [[ "$c" == "\\" ]]; then (( j++ ))
        elif [[ "$c" == "'" || "$c" == '"' ]]; then q="$c"
        elif [[ "$c" == '(' ]]; then (( depth++ ))
        elif [[ "$c" == ')' ]]; then (( depth-- ))
        fi
        (( j++ ))
      done
      (( depth == 0 )) || return 0
      body="${s:i+2:j-i-3}"
      printf '%s\n' "${body//$'\n'/ }"
      (( i = j )); continue
    fi
    if [[ "$c" == '`' ]]; then
      j=$(( i + 1 ))
      while (( j < n )) && [[ "${s:j:1}" != '`' ]]; do
        [[ "${s:j:1}" == "\\" ]] && (( j++ ))
        (( j++ ))
      done
      (( j < n )) || return 0
      body="${s:i+1:j-i-1}"
      printf '%s\n' "${body//$'\n'/ }"
      (( i = j + 1 )); continue
    fi
    (( i++ ))
  done
}

# True when the allocator would answer this segment with usage text and do nothing else: a bare
# `-h` / `--help` word after the script path (the allocator's own `_HELP_TOKENS` check). Quote
# state is carried across words, so a flag spelled inside a quoted value (`--reason "a --help b"`)
# is part of that value - the allocator never sees it as a flag, and neither does this check.
_alloc_help() {
  local -a toks=()
  read -r -a toks <<< "$1"
  local n=${#toks[@]} i=0 tok q="" k ch
  while (( i < n )); do
    [[ "${toks[i]//[\"\']/}" == *allocator.py ]] && break
    (( i++ ))
  done
  for (( i++; i < n; i++ )); do
    tok="${toks[i]}"
    if [[ -z "$q" ]]; then
      case "$tok" in -h|--help|\'-h\'|\'--help\'|\"-h\"|\"--help\") return 0 ;; esac
    fi
    for (( k = 0; k < ${#tok}; k++ )); do
      ch="${tok:k:1}"
      if [[ "$ch" == "\\" && "$q" != "'" ]]; then (( k++ )); continue; fi
      if [[ -z "$q" && ( "$ch" == "'" || "$ch" == '"' ) ]]; then q="$ch"
      elif [[ "$ch" == "$q" ]]; then q=""
      fi
    done
  done
  return 1
}

# Every segment the shell would EXECUTE: the logical segments of the command, plus - to a fixed
# depth - the logical segments of every command substitution inside any of them.
_executed_segments() {
  local pending="$1" next seg body level=0 all=""
  while [[ -n "$pending" ]] && (( level < 4 )); do
    all+="$pending"$'\n'
    next=""
    while IFS= read -r seg; do
      [[ -n "$seg" ]] || continue
      while IFS= read -r body; do
        [[ -n "$body" ]] || continue
        next+="$(printf '%s' "$body" | _logical_segments)"$'\n'
      done <<< "$(_cmd_substitutions "$seg")"
    done <<< "$pending"
    pending="$(printf '%s' "$next" | sed '/^[[:space:]]*$/d')"
    (( level++ ))
  done
  printf '%s' "$all"
}

SEGS="$(_executed_segments "$(printf '%s' "$CMD" | _logical_segments)")"

ARM=""
while IFS= read -r seg; do
  [[ -n "$seg" ]] || continue
  VERB="$(_alloc_verb "$seg")"
  [[ -n "$VERB" ]] || continue
  _alloc_help "$seg" && continue          # usage text only: nothing to own

  # A2 first: an override flag is refused whatever else the segment says, so threading a run id
  # cannot buy a --force.
  if [[ "$VERB" == "release" || "$VERB" == "park" ]] \
     && printf '%s' "$seg" | grep -qE '(^|[[:space:]])--force(-forget)?([[:space:]]|$)'; then
    ARM=A2; break
  fi
  if [[ "$VERB" == "reap-orphans" ]] \
     && printf '%s' "$seg" | grep -qE '(^|[[:space:]])--yes([[:space:]]|$)'; then
    ARM=A2; break
  fi
  # `acquire --allow-unowned` is the allocator's opt-out from naming an owner. It exists for a
  # human or a fixture that deliberately wants an ownerless lease; for a DISPATCHED agent it is
  # the wrong answer to the only question the refusal asks. An agent that reaches for it has no
  # run id, and the correct move is to say so upward - an ownerless lease is invisible to the run
  # that would otherwise clean up after it.
  if [[ "$VERB" == "acquire" ]] \
     && printf '%s' "$seg" | grep -qE '(^|[[:space:]])--allow-unowned([[:space:]]|$)'; then
    ARM=A2; break
  fi
  # A1: a release, park or adopt that names no owner.
  if [[ "$VERB" == "release" || "$VERB" == "park" || "$VERB" == "adopt" ]] \
     && ! printf '%s' "$seg" | grep -qE '(^|[[:space:]])--(run-id|session)([[:space:]]|=)'; then
    ARM=A1; break
  fi
  # A3: an APPLYING gc - anything but a dry run - over the machine-global registry.
  if [[ "$VERB" == "gc" ]] \
     && ! printf '%s' "$seg" | grep -qE '(^|[[:space:]])--dry-run([[:space:]]|=|$)'; then
    ARM=A3; break
  fi
done <<< "$SEGS"

if [[ -z "$ARM" ]]; then
  # A4, only once every lexical arm has passed: a release/park/adopt that names an owner, of a
  # token this agent does not hold.
  while IFS= read -r seg; do
    [[ -n "$seg" ]] || continue
    VERB="$(_alloc_verb "$seg")"
    [[ "$VERB" == "release" || "$VERB" == "park" || "$VERB" == "adopt" ]] || continue
    _alloc_help "$seg" && continue
    R="$(_a4_reason "allocator.py $VERB" "$(_alloc_token "$seg")" "$VERB")"
    [[ -n "$R" ]] && _deny "$R"
  done <<< "$SEGS"
  _pass
fi

if [[ "$ARM" == "A1" ]]; then
  REASON="REFUSED: you are \`$AGENT_NAME\`, and this \`allocator.py $VERB\` names no owner - no --run-id (nor its --session alias) anywhere in the command.

A release stops a server's process group and, for a \`drop_on_release\` lease, DROPS ITS DATABASE; a park stops the same process group. Both belong to the run that ACQUIRED the lease, so the call must name that run. An absent run id is not \"the owner forgot a flag\" - it is ownership not established, and this is the exact shape that destroyed a live acceptance database (see docs/reference/INSTANCE-ALLOCATION-GUARDS.md section 6.3).

DO THIS INSTEAD - take the branch that applies to you; do not simply re-send this call:
- If YOU acquired this lease you ALREADY HOLD its run id, and naming it is not rephrasing this command, it is supplying the ownership proof this gate exists to demand: your own acquire echoed it as ALLOC_RUN_ID, and a forwarded handle carries it as INSTANCE_HANDLE.run_id. If you cannot produce that value from something you actually received, you are not the owner - take the next branch.
- If you did NOT acquire it: LEAVE IT ALONE. Holding a token is not ownership, an absent owner.pid means liveness-not-verifiable rather than abandoned, and a lease from an earlier phase of the SAME run belongs to that run. Report it in your terminal status and let its owner - or allocator gc - deal with it.
- If your brief forwarded an INSTANCE_HANDLE to you, you are the CONSUMER, never the releaser (snippets/resource-teardown-contract.md T1).
- If you are trying to free the RAM but the database is still wanted, that is \`allocator.py park <token> --run-id <your run id>\`, not a release - it names its owner exactly as a release does.

This refusal is an ANSWER, not an obstacle - the same rule the override arm of this gate, snippets/resource-teardown-contract.md T4, agents/odoo-instance-ops.md and hooks/permission-denied-teardown.sh all state. Citing an owner you can actually produce is establishing ownership. Re-sending this call in a different SHAPE to get past the guard - rejoining or splitting lines, moving flags, re-encoding it, routing it through a script the gate does not read - is itself a blocked action. With no owner to cite, end your turn BLOCKED and quote this refusal."
elif [[ "$ARM" == "A3" ]]; then
  REASON="REFUSED: you are \`$AGENT_NAME\`, and this \`allocator.py gc\` would APPLY a reclaim (it carries no --dry-run). A dispatched agent may not run an applying gc.

The lease registry is MACHINE-GLOBAL: every session on this host shares it. An applying gc stops server process groups and DROPS databases across all of them, judged on liveness facts you cannot see from inside one dispatch - that is how live instances of other runs were destroyed. The only automatic applier is the SessionEnd hook, for the session that is actually ending.

DO THIS INSTEAD:
- To free what YOU obtained, release or park it by token: mcp__plugin_odoo-ai-agents_odoo-local__lease_release / lease_park (CLI fallback: \`allocator.py release <token> --run-id <your run id>\` / \`allocator.py park <token> --run-id <your run id>\`).
- To see what a janitor WOULD reclaim, run it with --dry-run (or lease_gc with dry_run: true) and report the candidates in your terminal status - applying them is the main context's decision, not yours.
- Never add --force to get past a refusal: --force on --scope anchor overrides a LIVE session's protection."
else
  REASON="REFUSED: you are \`$AGENT_NAME\`, and this \`allocator.py\` call carries an override flag (--force / --force-forget / --yes / --allow-unowned). A dispatched agent may not override the allocator's ownership decision.

Those flags exist to let a HUMAN reap a lease or database the ownership guard is protecting - which is exactly the judgement a dispatch cannot make: it cannot see the other sessions on this host, and the failure mode is irreversible (a dropped database, an abandoned one).

DO THIS INSTEAD: run the operation WITHOUT the override. If the allocator then refuses it, that refusal is your ANSWER, not an obstacle - end your turn with status BLOCKED (or NEEDS_NEXT naming who should decide) and quote the refusal, including the owning run it named. Never re-issue the same call with an override to get past it.

For \`--allow-unowned\` specifically the answer is upward, not sideways: you reached for it because you hold no run id, and the run id is something you should have been GIVEN. End your turn with NEEDS_CONTEXT(RUN_ID) naming the brief field that was missing. Do not invent an id either - an invented one is worse than none, because the lease then looks owned to the registry while being invisible to the only run that could release it."
fi

jq -cn --arg reason "$REASON" \
  '{hookSpecificOutput:{hookEventName:"PreToolUse", permissionDecision:"deny", permissionDecisionReason:$reason}}'
exit 0
