#!/usr/bin/env bash
# enforce-grounding.sh - SubagentStop enforcement substrate for odoo-ai-agents.
#
# WHY: the OSM-first contract, the odoo-coding ORM gate, and grounding labels are all
# ADVISORY prose today - an agent can emit `grounded: osm` without having made a single
# OSM call, and nothing notices. This hook turns the EXISTING contracts into a checkable
# invariant by reading the subagent's own transcript: if its report CLAIMS OSM grounding (its label
# line - see _grounding_labels) but the transcript shows ZERO `mcp__odoo-semantic__*` calls, that is
# a self-reported lie - block with corrective feedback (when, and how often: CONTRACT below). Softer
# gaps are surfaced as NON-blocking notes: a label line whose value is outside the contract's set;
# (a) backend .py written while OSM was reachable but the ORM validators never ran; and
# (b) the silent-skipper - backend .py written with ZERO OSM calls and no grounding label
# at all. Neither (a) nor (b) is a provable lie (so never blocked, per the agent-consumer debate: a block
# there only manufactures fake labels the hook cannot verify), but they must not slip through
# unnoticed - hence notes that teach the honest paths. When such a note fires AND the subagent
# never read a coding_guidelines/<version>/ file, a read-before-write reminder rides along
# ($GUIDELINES_NOTE). The reminder is NOT its own invariant: nagging an honest, fully-grounded
# subagent would break the "honest work passes clean" contract. The primary enforcement for
# guidelines is the agent-prompt read-before-write gate, not read-count.
#
# CONTRACT (Claude Code SubagentStop): stdin JSON has agent_transcript_path (the subagent's own
# transcript - the one read here), transcript_path (the whole session's) + stop_hook_active.
#   - Checks EVERY stop, a continued one included (stop_hook_active=true): a note or a block buys
#     the subagent one more turn, and the report it writes there is the one its caller receives, so
#     that report is checked like the first. Loop-safe instead: a note is said at most once per
#     context window (hooks/advice-once.sh _stop_text_due), and a block is given on every stop no
#     hook continued - a caller's resume is a new report - but at most once inside one
#     hook-continued chain (_stop_block_due; the harness records a block reason in the transcript).
#   - Block form: {"decision":"block","reason":"..."} on stdout (forces the subagent to fix); the
#     reason ends on the sentence that tells it what its caller receives after that extra turn.
#   - Note form: SubagentStop additionalContext to the subagent (it reads it and runs one more
#     turn); nothing once the report was handed back - see _note.
#   - Self-gating: acts ONLY on Odoo-shaped subagents (OSM usage / .py writes / grounding
#     vocabulary in the transcript); silently approves anything else - it must never disrupt
#     unrelated subagents from other plugins.
#   - Degrades to exit 0 on any uncertainty (no jq, no transcript, parse error).

set -uo pipefail

_pass() { exit 0; }   # approve / stay out of the way

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"

# Shared helpers: hooks/final-report.sh (which transcript, and the agent's own signals) and
# hooks/advice-once.sh (is this text already in the context - the loop guard). Unreadable -> pass.
_FR_LIB="${BASH_SOURCE[0]%/*}/final-report.sh"
[[ -r "$_FR_LIB" && -r "${BASH_SOURCE[0]%/*}/advice-once.sh" ]] || _pass
# shellcheck source=/dev/null
. "$_FR_LIB"
# shellcheck source=/dev/null
. "${BASH_SOURCE[0]%/*}/advice-once.sh"
# Optional: hooks/teammate-wait.sh tells a stop that only WAITS for a teammate apart from a final
# report, so the closing sentence of a note or block fits it. Unreadable -> every stop is a report.
# shellcheck source=/dev/null
[[ -r "${BASH_SOURCE[0]%/*}/teammate-wait.sh" ]] && . "${BASH_SOURCE[0]%/*}/teammate-wait.sh"

# The subagent's OWN transcript (agent_transcript_path on SubagentStop - never the session-wide
# transcript_path, which would credit the parent's or a sibling's OSM calls to this subagent).
TRANSCRIPT="$(_hook_transcript "$INPUT")"
[[ -n "$TRANSCRIPT" ]] || _pass

# --- Signals from the subagent's own transcript (ASSISTANT-authored only) -------------------
# final-report.sh _assistant_signals: tool CALLS are counted from real `tool_use` blocks (not a
# tool name mentioned in an instruction or tool_result). The grounding LABEL is read from the report
# alone (_grounding_labels below), never from an injected contract snippet or brief that quotes one.
# Tolerant: on any jq failure NORM is empty -> self-gate -> no enforcement.
NORM="$(_assistant_signals "$TRANSCRIPT" "$(_hook_last_message "$INPUT")")"

_cnt() { printf '%s\n' "$NORM" | grep -ciE "$1" 2>/dev/null | tr -d '[:space:]' || true; }
OSM_CALLS=$(_cnt $'^CALL\tmcp__odoo-semantic__')
VALIDATOR_CALLS=$(_cnt $'^CALL\tmcp__odoo-semantic__(validate_depends|validate_domain|validate_relation|resolve_orm_chain)')
# Backend .py writes: a Write/Edit/MultiEdit tool_use whose path ends in .py.
PY_WRITES=$(_cnt $'^CALL\t(Write|Edit|MultiEdit)\t.*\\.py$')
# Read-before-write signal: did the subagent open a coding_guidelines/<version>/ file?
GUIDELINES_READ=$(_cnt $'^CALL\t(Read|Grep)\t.*coding_guidelines')
# The grounding LABEL (osm-first-contract.md section 5): a line of the report the caller receives
# (final-report.sh _final_report_text) that starts with the `grounded:` key - after indentation, a
# list or blockquote marker, with bold or backticks around the key alone - outside any code fence.
# Its VALUE is the first word after the key, words being split at every character other than a
# letter, digit, `_`, `-` or `=` (so `(osm)`, `osm+local-source` and `osm/disk` read `osm`, while
# `osm-verified` stays one word): `osm` or `hybrid` claim OSM grounding; `local-source`,
# `ungrounded` and `unknown` are honest; a tally of `<key>=<n>` words, in any order, claims OSM
# when its osm or hybrid count is above zero - even beside a key outside the set - and is honest
# otherwise. Everything after the value is explanation the gate never reads. Any other value, or a
# tally key outside the set, is MALFORMED and earns a note; a malformed value claims nothing.
# Everywhere else the label is a mention - quoted whole, mid-sentence, in a table or JSON, in a
# fence, another agent's output - and an earlier report, already replaced, is not what the caller
# receives. Prints "<claims> <honest> <malformed>", one count per line.
_grounding_labels() {
  printf '%s\n' "$1" | awk '
    /^[ \t]*(```|~~~)/ { fence = !fence; next }
    fence { next }
    {
      line = tolower($0)
      sub(/^[ \t]+/, "", line)
      while (sub(/^>[ \t]*/, "", line)) {}
      sub(/^([-*+]|[0-9]+[.)])[ \t]+/, "", line)
      if (!match(line, /^((\*\*|__)?grounded(\*\*|__)?|`grounded`):(\*\*|__)?[ \t]*/)) next
      rest = substr(line, RLENGTH + 1)
      gsub(/[^a-z0-9_=-]+/, " ", rest)
      sub(/^ +/, "", rest)
      nw = split(rest, w, / +/)
      v = w[1]
      if (v ~ /^[a-z_-]+=[0-9]+$/) {
        claim = 0; bad = 0
        for (i = 1; i <= nw; i++) {
          if (w[i] !~ /^[a-z_-]+=[0-9]+$/) break
          split(w[i], kv, "=")
          if (kv[1] !~ /^(osm|hybrid|local-source|ungrounded|unknown)$/) bad = 1
          else if ((kv[1] == "osm" || kv[1] == "hybrid") && kv[2] + 0 > 0) claim = 1
        }
        if (claim) c++; else if (!bad) h++
        if (bad) m++
      } else if (v == "osm" || v == "hybrid") c++
      else if (v == "local-source" || v == "ungrounded" || v == "unknown") h++
      else m++
    }
    END { print c + 0, h + 0, m + 0 }' 2>/dev/null || echo "0 0 0"
}
read -r CLAIMS_OSM CLAIMS_LOCAL LABELS_MALFORMED < <(_grounding_labels \
  "$(_final_report_text "$TRANSCRIPT" "$(_hook_last_message "$INPUT")")")
[[ "$CLAIMS_OSM" =~ ^[0-9]+$ ]] || CLAIMS_OSM=0
[[ "$CLAIMS_LOCAL" =~ ^[0-9]+$ ]] || CLAIMS_LOCAL=0
[[ "$LABELS_MALFORMED" =~ ^[0-9]+$ ]] || LABELS_MALFORMED=0

# Read-before-write reminder clause, appended to PY-write notes when no guidelines file was read.
GUIDELINES_NOTE=""
if [[ "$PY_WRITES" -gt 0 && "$GUIDELINES_READ" -eq 0 ]]; then
    GUIDELINES_NOTE=" Read-before-write note: no skills/_shared/coding_guidelines/<version>/ file was read in this subagent. Per the read-before-write rule, the version's coding guidelines (naming prefixes, model attribute order, import order, _() form) must be read BEFORE writing so the code is correct on the first pass."
fi

# Self-gate: only Odoo-shaped subagents are our concern.
if [[ "$OSM_CALLS" -eq 0 && "$PY_WRITES" -eq 0 && "$CLAIMS_OSM" -eq 0 && "$CLAIMS_LOCAL" -eq 0 \
      && "$LABELS_MALFORMED" -eq 0 ]]; then
    _pass
fi

# --- Invariant 1 (BLOCK): claims OSM grounding but made zero OSM calls ----------------------
if [[ "$CLAIMS_OSM" -gt 0 && "$OSM_CALLS" -eq 0 ]]; then
    # The block buys the subagent one more turn whose last message replaces its report for the
    # caller, so the reason ends on the sentence that says so (final-report.sh _subagent_note_tail).
    # A fresh stop is always checked; inside a hook-continued chain this exact refusal is given once
    # (hooks/advice-once.sh _stop_block_due), so a block the subagent ignores cannot loop.
    REASON="Grounding invariant violated: your report's \`grounded:\` label line claims OSM but this subagent's transcript shows ZERO mcp__odoo-semantic__* calls. Either actually verify the claim against OSM (set_active_version + model_inspect/entity_lookup/etc.), or relabel honestly: \`grounded: local-source - <why>\` when you read the source, \`grounded: ungrounded - <why>\` when nothing was checked (osm-first-contract.md section 5: the first word after the key is the value, the rest is explanation). Your report carries one label line, for its own work: describe an earlier label in prose, never on a label line. Do not assert OSM grounding you did not perform. $(_subagent_note_tail "$TRANSCRIPT" "$INPUT")"
    _stop_block_due "$TRANSCRIPT" "$STOP_ACTIVE" "$REASON" || _pass
    jq -cn --arg r "$REASON" '{decision:"block", reason:$r}'
    exit 0
fi

# A NON-BLOCKING note goes to the subagent, the one agent that can still act on it before its report
# reaches the caller: SubagentStop additionalContext, which the subagent reads and answers in ONE
# more turn (a SubagentStop systemMessage reaches neither the subagent nor its caller). The note then
# says that the caller receives the message that turn ends on (final-report.sh _subagent_note_tail).
# A report already delivered through SubagentHandback cannot change any more, and no SubagentStop
# channel reaches anyone else, so there the note is not emitted at all. Said once per context window
# (hooks/advice-once.sh _stop_text_due): a subagent woken again after a stop would otherwise get the
# same note at every later stop.
_note() {
  _handback_delivered "$TRANSCRIPT" && _pass
  _stop_text_due "$TRANSCRIPT" "$STOP_ACTIVE" "$1" || _pass
  jq -cn --arg m "$1 $(_subagent_note_tail "$TRANSCRIPT" "$INPUT")" \
    '{hookSpecificOutput: {hookEventName: "SubagentStop", additionalContext: $m}}'
  exit 0
}

# --- Malformed label (NON-BLOCKING note): a label line whose value is outside the contract's set
# claims nothing, so it can hide neither a lie nor an honest label - tell the subagent the form.
if [[ "$LABELS_MALFORMED" -gt 0 ]]; then
    _note "Grounding label note: your report has a \`grounded:\` line whose first word after the key is not one of osm | hybrid | local-source | ungrounded | unknown or a <key>=<n> tally, so it states no grounding. Write it as \`grounded: <value> - <explanation>\` (osm-first-contract.md section 5), e.g. \`grounded: ungrounded - OSM unavailable\`."
fi

# --- Invariant 2 (NON-BLOCKING note): backend code written, OSM reachable, validators skipped
if [[ "$PY_WRITES" -gt 0 && "$OSM_CALLS" -gt 0 && "$VALIDATOR_CALLS" -eq 0 && "$CLAIMS_LOCAL" -eq 0 ]]; then
    _note "Quality-gate note: backend Python was written and OSM was reachable, but no ORM validators (validate_depends/validate_domain/resolve_orm_chain/validate_relation) ran in this subagent. Per agents/odoo-backend-coder.md Round 5, run the ORM validation gate before presenting, or label your work \`grounded: local-source - <why>\` (the /test_lint lint-class gate is NOT yours - it runs once at run-harness's pre-PR tail). Also confirm currency of touched core symbols via lookup_core_api (existence is not currency).${GUIDELINES_NOTE}"
fi

# --- Invariant 3 (NON-BLOCKING note): the silent-skipper -------------------------------------
# Backend .py written with ZERO OSM calls AND no grounding label. Mutually exclusive with
# Invariant 2 (which needs OSM_CALLS>0). Deliberately a note, not a block: absence of an OSM
# call is not a provable lie, the hook sees only THIS subagent's transcript (grounding may have
# happened upstream), and many .py writes legitimately need no OSM (util/migration/test/
# __init__/__manifest__/data, or OSM simply unreachable). Blocking those would false-block real
# work and pressure the agent into emitting an unverifiable `grounded: local-source`. So: nudge,
# don't gate - the hard quality gate is /test_lint/CI (behavior), not OSM-call-count.
if [[ "$PY_WRITES" -gt 0 && "$OSM_CALLS" -eq 0 && "$CLAIMS_OSM" -eq 0 && "$CLAIMS_LOCAL" -eq 0 ]]; then
    _note "Grounding note: this subagent wrote backend Python (.py) but made ZERO mcp__odoo-semantic__* calls and emitted no grounding label. If the file touches ORM (models/fields/@api.depends/domain=/related=), ground it before presenting - set_active_version + model_inspect/entity_lookup to verify, then the Round-4 ORM validators + the /test_lint backend lint gate - or, if OSM is unreachable, ground against disk and label \`grounded: local-source - OSM unreachable\`. If the file is pure-Python with no ORM (util/migration/test/__init__/__manifest__/data), label it \`grounded: ungrounded - pure Python, no ORM\`, so the grounding gate is satisfied. Don't leave Odoo backend code silently ungrounded. Also confirm currency of touched core symbols via lookup_core_api (existence is not currency).${GUIDELINES_NOTE}"
fi

# NOTE: the read-before-write reminder is appended to Invariants 2/3 (via $GUIDELINES_NOTE), not
# emitted as its own invariant. A standalone note would nag honest, fully-grounded subagents that
# simply did not read a guidelines file - which contradicts the "honest work passes clean"
# contract. The primary read-before-write enforcement is the agent-prompt gate; the hook only adds
# the reminder when it is ALREADY nudging for a grounding gap.

_pass
