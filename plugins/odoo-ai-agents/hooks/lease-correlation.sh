# lease-correlation.sh - SOURCED helper (not a hook): the ONE implementation of "which instance
# leases does THIS agent's own transcript prove it holds". Two gates read it and must never
# disagree:
#   - enforce-teardown.sh (SubagentStop): a live lease the subagent OBTAINED blocks its turn end.
#   - block-unowned-lease-mutation.sh (PreToolUse): a subagent may release/park/adopt only a lease
#     it OBTAINED, or one a child it dispatched HANDED UP to it (an adopt also a token its own
#     lease_find returned - _lease_found_text).
# If the two drifted, the teardown gate could order a release the mutation gate then refuses (a
# deadlock), or accept a release of a lease the mutation gate should have protected.
#
# Every function takes the path of the agent's OWN transcript (a JSONL file) and prints to stdout;
# on any failure (no jq, unreadable file, parse error) it prints nothing. Callers decide what
# "nothing" means - both gates treat it as uncertainty and fail open.
#
# WHAT COUNTS AS OBTAINED (_lease_owned_tokens) - read from the tool RESULTS of the agent's OWN
# calls, paired to the call by tool_use_id, never from a run id (a run id is shared by the parent
# and every sibling of one run by design). Each only when its result is not an error:
#   - Bash `allocator.py acquire`   -> `ALLOC_TOKEN=<tok>` (shell protocol) or `"ALLOC_TOKEN":
#                                      "<tok>"` (--format json) in that call's own tool_result, and
#                                      the allocator's stderr receipt `allocator: acquired lease
#                                      <tok> run_id=<id>`. The receipt is what makes the eval shape
#                                      `eval "$(allocator.py acquire ...)"` correlatable at all: its
#                                      stdout lands in shell variables, but stderr still reaches the
#                                      tool_result, and it names the ONE token that very call got.
#   - Bash `allocator.py adopt <tok>` -> the literal token argument, and the stderr receipt
#                                      `allocator: adopted lease <tok> run_id=<id>`.
#   - odoo-local `lease_acquire`    -> `.lease.token` (or `.token`) of its result JSON.
#   - odoo-local `lease_adopt`      -> the `lease_token` (or `token`) argument, and the
#                                      `lease_token` its result reports (a deliberate take-over).
#   - odoo-local `instance_serve`   -> ONLY a serve called WITHOUT an input `lease_token` (series
#                                      mode) whose result reports `state: "launched"`, and then only
#                                      the `lease_token` that result reports - the server that very
#                                      call STARTED, and the lease it registered for it. That lease
#                                      is always `shared` (series mode registers no other kind), so
#                                      only arm A4 acts on it - the launcher may stop the server on
#                                      an explicit user request; the teardown gate never lists a
#                                      shared lease.
# NOT obtainment, on purpose: `instance_serve {lease_token: <tok>}`, Bash `allocator.py resume
# <tok>`, and a series-mode serve whose result reports `state: "attached"`. An attach joined a
# server some OTHER run already started; counting the token it reports made that run's server this
# caller's to release, and a release stops it under everyone still using it. A consumer of a forwarded INSTANCE_HANDLE is TOLD to ensure its instance is up by serving
# the handle's lease_token (resource-teardown-contract.md T0 (b) counts only "an instance_serve that
# leased it for you"), so counting that input token named the PARENT's lease as the child's - and
# since the child shares the parent's run id, following a release command for it would have
# succeeded and destroyed the instance the parent still holds. Serving or resuming a token you were
# handed is consumption; only acquire, adopt and a LAUNCHING series-mode serve move a lease into
# this agent's hands. Resuming a PARKED lease of your own run from a new session therefore goes
# lease_find -> lease_adopt -> instance_serve: the adopt is the explicit take-over that makes it
# this agent's to park or release (a lease_find token is adopt-only - _lease_found_text).
#
# There is NO time-window fallback. An eval-shape acquire whose tool_result carries no receipt (an
# allocator that predates it) correlates to nothing - a false negative. The window it replaced
# ("every lease of that run acquired within +/- N s of the call") named every PARALLEL SIBLING of
# the same run that acquired in the same seconds, which is the run-id defect again.
#
# The scan reads RAW transcript lines: tool_result blocks are harness-authored `user` records. Only
# an ASSISTANT tool_use can open a correlation, so a tool_result that merely quotes a token never
# counts on its own, and a receipt line is read only from the result of an allocator acquire/adopt
# call - a `cat` of some log that happens to contain one proves nothing about this agent.
#
# WHAT COUNTS AS HANDED UP (_lease_handed_up_text) - the report a CHILD this agent dispatched
# returned to it: the tool_result of its own synchronous `Agent` / `Task` call; the harness's
# `task-notification` record (origin.kind) whose <tool-use-id> is one of its own Agent/Task calls,
# <result> body only; and a PEER message from that child (origin.kind "peer", origin.from = the
# child's agentId). A child whose report travels in the `SubagentHandback` tool reaches
# its caller ONLY as a peer message (origin.handback true) - the Agent result and the notification
# then just point at it - and any later message from that child arrives the same way, so both
# count. The harness writes a peer message either as a `user` record
# carrying `origin`, or, while the caller is blocked on a synchronous Agent call, as an
# `attachment` record of type `queued_command` carrying `attachment.origin`. A child is identified
# by the `agentId` its launch result (toolUseResult) reports for one of this agent's OWN Agent/Task
# calls - a peer message from anyone else (the caller, a sibling) is never a hand-up. An ASYNC
# launch result's TEXT is excluded on purpose: it echoes the PROMPT this agent sent DOWN, and a
# token forwarded down to a grandchild is still not this agent's.
#
# WHAT COUNTS AS FORWARDED DOWN (_lease_brief_text) - the user-role text this agent was GIVEN: its
# dispatch brief and any later message from its caller, including a peer message (either record
# shape above) from anyone who is NOT a child it dispatched (never a tool_result, never a
# notification, never a child's hand-up). Used only to word a refusal; being named there is never
# ownership.

# Shared jq prelude for the two functions above: $L = every record, $ids = this agent's own
# Agent/Task tool_use ids, $kids = the agentIds of the children those calls launched, and
# `peer_envelope` = a record's peer-message envelope ({from, text}) in either on-disk shape, or null.
_LEASE_JQ_KIDS='
  def blocktext: if type == "string" then . elif type == "array" then (map(.text? // "" | strings) | join("\n")) else "" end;
  def peer_envelope: if ((.origin.kind // "") == "peer") then
              {from: ((.origin.from // "") | tostring),
               text: ([(.origin.body // empty), ((.message // .).content // "" | blocktext)]
                      | map(strings) | join("\n"))}
            elif ((.attachment.type // "") == "queued_command" and ((.attachment.origin.kind // "") == "peer")) then
              {from: ((.attachment.origin.from // "") | tostring),
               text: ([(.attachment.origin.body // empty), (.attachment.prompt // empty)]
                      | map(strings) | join("\n"))}
            else null end;
  [split("\n")[] | fromjson? | objects] as $L
  | ([ $L[]
       | (.message // .) as $m | select((($m.role // .type) // "") == "assistant")
       | ($m.content // []) | (if type == "array" then .[] else empty end)
       | select(.type == "tool_use" and (((.name // "") | tostring) | test("^(Agent|Task)$")))
       | (.id // "") | select(. != "") ]) as $ids
  | ([ $L[] | . as $r
       | (($r.message // $r).content // []) | (if type == "array" then .[] else empty end)
       | select(.type == "tool_result" and ((.tool_use_id // "") as $x | ($ids | any(. == $x))))
       | ($r.toolUseResult.agentId // $r.toolUseResult.agent_id // empty) | strings
       | select(. != "") ]) as $kids
'

_lease_owned_tokens() {
  local transcript="$1"
  command -v jq >/dev/null 2>&1 || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || return 0
  jq -rRs '
  def texts: [.. | strings];
  def tok_re: "^[A-Za-z0-9_-]{8,}$";
  def receipt($verb): scan("allocator: " + $verb + " lease ([A-Za-z0-9_-]{8,})") | .[0];
  [split("\n")[] | fromjson? | objects] as $L
  | ([ $L[]
       | (.message // .) as $m | select((($m.role // .type) // "") == "assistant")
       | ($m.content // []) | (if type == "array" then .[] else empty end)
       | select(.type == "tool_use")
       | {id: (.id // ""), name: ((.name // "") | tostring), input: (.input // {})} ]) as $uses
  | ([ $L[] | . as $r
       | (.message // .) as $m
       | ($m.content // []) | (if type == "array" then .[] else empty end)
       | select(.type == "tool_result")
       | {id: (.tool_use_id // ""), err: (.is_error == true),
          strs: ((. | texts) + (($r.toolUseResult // null) | texts)),
          objs: [($r.toolUseResult // null) | objects]} ]) as $results
  # Each tool_use_id -> its FIRST result, built in one pass, so pairing a call with its result is
  # a lookup: scanning every result per call is quadratic, and on a transcript with thousands of
  # calls that alone outruns the timeout of a hook.
  | (reduce $results[] as $x ({};
       if ($x.id != "" and (has($x.id) | not)) then .[$x.id] = $x else . end)) as $by_id
  | $uses[] as $u
  | (if $u.id != "" then $by_id[$u.id] else null end) as $res
  | select($res != null and ($res.err | not))
  | ($u.input.command // "" | tostring) as $cmd
  | if $u.name == "Bash" then
      (if ($cmd | test("allocator\\.py[^[:space:]A-Za-z0-9_-]?[[:space:]]+acquire([[:space:]]|$)")) then
         ($res.strs[] | scan("ALLOC_TOKEN[^[:space:]A-Za-z0-9_-]?[[:space:]]*[=:][[:space:]]*[^[:space:]A-Za-z0-9_-]?([A-Za-z0-9_-]{8,})") | .[0]),
         ($res.strs[] | receipt("acquired"))
       else empty end),
      (if ($cmd | test("allocator\\.py[^[:space:]A-Za-z0-9_-]?[[:space:]]+adopt([[:space:]]|$)")) then
         ($cmd | scan("allocator\\.py[^[:space:]A-Za-z0-9_-]?[[:space:]]+adopt[[:space:]]+[^[:space:]A-Za-z0-9_-]?([A-Za-z0-9_-]{8,})") | .[0]),
         ($res.strs[] | receipt("adopted"))
       else empty end)
    elif ($u.name | test("odoo-local__lease_acquire$")) then
      ([ ($res.objs[] | (.structuredContent // .)),
         ($res.strs[] | fromjson? | objects) ]
       | map((.lease.token // .token // .structuredContent.lease.token // empty) | strings)
       | unique[] | select(test(tok_re)))
    elif ($u.name | test("odoo-local__lease_adopt$")) then
      ([ ($u.input.lease_token // $u.input.token // empty),
         (($res.objs[] | (.structuredContent // .)), ($res.strs[] | fromjson? | objects)
          | (.lease_token // .lease.token // empty)) ]
       | map(strings | select(test(tok_re))) | unique[])
    elif ($u.name | test("odoo-local__instance_serve$"))
         and ((($u.input.lease_token // $u.input.token // "") | tostring) == "") then
      ([ ($res.objs[] | (.structuredContent // .)), ($res.strs[] | fromjson? | objects)
         | select((.state // "") == "launched")
         | (.lease_token // empty) ]
       | map(strings | select(test(tok_re))) | unique[])
    else empty end
  ' "$transcript" 2>/dev/null | sort -u || true
}

_lease_handed_up_text() {
  local transcript="$1"
  command -v jq >/dev/null 2>&1 || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || return 0
  jq -rRs "$_LEASE_JQ_KIDS"'
  | $L[] | . as $r
  | ($r | peer_envelope) as $p
  | if $p != null then
      select($p.from != "" and ($kids | any(. == $p.from))) | $p.text
    elif (($r.origin.kind // "") == "task-notification") then
      (($r.message // $r).content // "" | blocktext) as $t
      | ($t | [scan("<tool-use-id>([^<]+)</tool-use-id>") | .[0]]) as $tids
      | select(any($tids[]; . as $x | ($ids | any(. == $x))))
      | ($t | [scan("(?s)<result>(.*?)</result>") | .[0]] | join("\n"))
    else
      (($r.message // $r).content // []) | (if type == "array" then .[] else empty end)
      | select(.type == "tool_result" and ((.tool_use_id // "") as $x | ($ids | any(. == $x))))
      | select((.is_error == true) | not)
      | select((($r.toolUseResult.status // "") != "async_launched") and (($r.toolUseResult.isAsync // false) != true))
      | (.content // "" | blocktext)
    end
  ' "$transcript" 2>/dev/null || true
}

_lease_brief_text() {
  local transcript="$1"
  command -v jq >/dev/null 2>&1 || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || return 0
  jq -rRs "$_LEASE_JQ_KIDS"'
  | $L[] | . as $r
  | ($r | peer_envelope) as $p
  | if $p != null then
      select(($kids | any(. == $p.from)) | not) | $p.text
    else
      select((($r.origin.kind // "") != "task-notification"))
      | ($r.message // $r) as $m | select((($m.role // $r.type) // "") == "user")
      | ($m.content // "")
      | if type == "string" then . elif type == "array" then (.[] | select(.type == "text") | (.text // "")) else empty end
    end
  ' "$transcript" 2>/dev/null || true
}

# The result text of the agent's OWN successful `lease_find` calls (odoo-local). lease_find returns
# a full token only for a parked lease of the caller's own run, so a token found here is one the
# agent may ADOPT to resume from a new session - never grounds for a release or park.
_lease_found_text() {
  local transcript="$1"
  command -v jq >/dev/null 2>&1 || return 0
  [[ -n "$transcript" && -r "$transcript" ]] || return 0
  jq -rRs '
  [split("\n")[] | fromjson? | objects] as $L
  | ([ $L[]
       | (.message // .) as $m | select((($m.role // .type) // "") == "assistant")
       | ($m.content // []) | (if type == "array" then .[] else empty end)
       | select(.type == "tool_use" and (((.name // "") | tostring) | test("odoo-local__lease_find$")))
       | (.id // "") | select(. != "") ]) as $ids
  | $L[] | . as $r
  | (($r.message // $r).content // []) | (if type == "array" then .[] else empty end)
  | select(.type == "tool_result" and ((.tool_use_id // "") as $x | ($ids | any(. == $x))))
  | select((.is_error == true) | not)
  | ([.. | strings] + [($r.toolUseResult // null) | .. | strings]) | join("\n")
  ' "$transcript" 2>/dev/null || true
}

# The transcript of the agent a PreToolUse payload comes from. `agent_transcript_path` when the
# harness supplies it; otherwise the harness's on-disk layout, `<session transcript minus .jsonl>/
# subagents/agent-<agent_id>.jsonl`. Prints nothing when neither resolves to a readable file.
_lease_agent_transcript() {
  local input="$1" p sess aid
  command -v jq >/dev/null 2>&1 || return 0
  p="$(printf '%s' "$input" | jq -r '.agent_transcript_path // empty' 2>/dev/null || true)"
  if [[ -n "$p" && -r "$p" ]]; then printf '%s\n' "$p"; return 0; fi
  sess="$(printf '%s' "$input" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
  aid="$(printf '%s' "$input" | jq -r '.agent_id // .agentId // empty' 2>/dev/null || true)"
  [[ -n "$sess" && -n "$aid" ]] || return 0
  p="${sess%.jsonl}/subagents/agent-${aid}.jsonl"
  [[ -r "$p" ]] && printf '%s\n' "$p"
  return 0
}
