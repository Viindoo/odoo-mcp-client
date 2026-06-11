#!/usr/bin/env bash
# enforce-grounding.sh — SubagentStop enforcement substrate for odoo-ai-agents.
#
# WHY: the OSM-first contract, the odoo-coding ORM gate, and grounding labels are all
# ADVISORY prose today — an agent can emit `grounded: osm` without having made a single
# OSM call, and nothing notices. This hook turns the EXISTING contracts into a checkable
# invariant by reading the subagent's own transcript: if the artifact CLAIMS OSM grounding
# but the transcript shows ZERO `mcp__odoo-semantic__*` calls, that is a self-reported lie —
# block once with corrective feedback. Softer gaps are surfaced as NON-blocking notes:
# (a) backend .py written while OSM was reachable but the ORM validators never ran; and
# (b) the silent-skipper — backend .py written with ZERO OSM calls and no grounding label
# at all. Neither is a provable lie (so never blocked, per the agent-consumer debate: a block
# there only manufactures fake labels the hook cannot verify), but they must not slip through
# unnoticed — hence notes that teach the honest paths. When such a note fires AND the subagent
# never read a coding_guidelines/<version>/ file, a read-before-write reminder rides along
# ($GUIDELINES_NOTE). The reminder is NOT its own invariant: nagging an honest, fully-grounded
# subagent would break the "honest work passes clean" contract. The primary enforcement for
# guidelines is the agent-prompt read-before-write gate, not read-count.
#
# CONTRACT (Claude Code SubagentStop): stdin JSON has transcript_path + stop_hook_active.
#   - Loop-safe: when stop_hook_active=true we already forced one continue — never re-block.
#   - Block form: {"decision":"block","reason":"..."} on stdout (forces the subagent to fix).
#   - Self-gating: acts ONLY on Odoo-shaped subagents (OSM usage / .py writes / grounding
#     vocabulary in the transcript); silently approves anything else — it must never disrupt
#     unrelated subagents from other plugins.
#   - Degrades to exit 0 on any uncertainty (no jq, no transcript, parse error).

set -uo pipefail

_pass() { exit 0; }   # approve / stay out of the way

command -v jq >/dev/null 2>&1 || _pass
INPUT="$(cat 2>/dev/null || true)"
[[ -n "$INPUT" ]] || _pass

STOP_ACTIVE="$(printf '%s' "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null || echo false)"
[[ "$STOP_ACTIVE" == "true" ]] && _pass   # already continuing from a prior block — no loop

TRANSCRIPT="$(printf '%s' "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
[[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]] || _pass

# --- Signals from the subagent's own transcript (ASSISTANT-authored only) -------------------
# Parse the jsonl into a normalized stream so that tool CALLS are counted from real `tool_use`
# blocks (not a tool name mentioned in an instruction or tool_result) and grounding LABELS are
# read only from the ASSISTANT's own text — never from an injected contract snippet that quotes
# the label (e.g. osm-first-contract.md §5 contains the literal "grounded: osm"). Tolerant:
# `fromjson?` skips non-JSON lines; on any jq failure NORM is empty → self-gate → no enforcement.
NORM="$(jq -rR 'fromjson? | (.message // .) as $m
  | (($m.role // .type) // "") as $role
  | select($role == "assistant")
  | ($m.content // [])
  | (if type == "array" then .[] else empty end)
  | if (.type == "tool_use") then
        "CALL\t" + ((.name // "")|tostring) + "\t" + ((.input.file_path // .input.path // "")|tostring)
    elif (.type == "text") then
        "TEXT\t" + ((.text // "")|tostring)
    else empty end' "$TRANSCRIPT" 2>/dev/null || true)"

_cnt() { printf '%s\n' "$NORM" | grep -ciE "$1" 2>/dev/null | tr -d '[:space:]' || true; }
OSM_CALLS=$(_cnt $'^CALL\tmcp__odoo-semantic__')
VALIDATOR_CALLS=$(_cnt $'^CALL\tmcp__odoo-semantic__(validate_depends|validate_domain|validate_relation|resolve_orm_chain)')
# Backend .py writes: a Write/Edit/MultiEdit tool_use whose path ends in .py.
PY_WRITES=$(_cnt $'^CALL\t(Write|Edit|MultiEdit)\t.*\\.py$')
# Read-before-write signal: did the subagent open a coding_guidelines/<version>/ file?
GUIDELINES_READ=$(_cnt $'^CALL\t(Read|Grep)\t.*coding_guidelines')
# Grounding-label vocabulary (osm-first-contract.md §4), from assistant text only.
CLAIMS_OSM=$(_cnt $'^TEXT\t.*grounded:[[:space:]]*osm')
CLAIMS_LOCAL=$(_cnt $'^TEXT\t.*(grounded:[[:space:]]*local-source|OSM unavailable|standalone)')

# Read-before-write reminder clause, appended to PY-write notes when no guidelines file was read.
GUIDELINES_NOTE=""
if [[ "$PY_WRITES" -gt 0 && "$GUIDELINES_READ" -eq 0 ]]; then
    GUIDELINES_NOTE=" Read-before-write note: no skills/_shared/coding_guidelines/<version>/ file was read in this subagent. Per the read-before-write rule, the version's coding guidelines (naming prefixes, model attribute order, import order, _() form) must be read BEFORE writing so the code is correct on the first pass."
fi

# Self-gate: only Odoo-shaped subagents are our concern.
if [[ "$OSM_CALLS" -eq 0 && "$PY_WRITES" -eq 0 && "$CLAIMS_OSM" -eq 0 && "$CLAIMS_LOCAL" -eq 0 ]]; then
    _pass
fi

# --- Invariant 1 (BLOCK): claims OSM grounding but made zero OSM calls ----------------------
if [[ "$CLAIMS_OSM" -gt 0 && "$OSM_CALLS" -eq 0 ]]; then
    jq -cn --arg r "Grounding invariant violated: the artifact claims \`grounded: osm\` but this subagent's transcript shows ZERO mcp__odoo-semantic__* calls. Either actually verify the claim against OSM (set_active_version + model_inspect/entity_lookup/etc.), or relabel honestly as \`grounded: local-source (not OSM-indexed)\` / \`OSM unavailable - ungrounded\` per osm-first-contract.md §4. Do not assert OSM grounding you did not perform." \
        '{decision:"block", reason:$r}'
    exit 0
fi

# --- Invariant 2 (NON-BLOCKING note): backend code written, OSM reachable, validators skipped
if [[ "$PY_WRITES" -gt 0 && "$OSM_CALLS" -gt 0 && "$VALIDATOR_CALLS" -eq 0 && "$CLAIMS_LOCAL" -eq 0 ]]; then
    jq -cn --arg m "Quality-gate note: backend Python was written and OSM was reachable, but no ORM validators (validate_depends/validate_domain/resolve_orm_chain/validate_relation) ran in this subagent. Per agents/odoo-coder.md Round 4, run the ORM gate + scripts/verify-backend.sh before presenting, or label standalone-mode explicitly.${GUIDELINES_NOTE}" \
        '{continue:true, systemMessage:$m}'
    exit 0
fi

# --- Invariant 3 (NON-BLOCKING note): the silent-skipper -------------------------------------
# Backend .py written with ZERO OSM calls AND no grounding label. Mutually exclusive with
# Invariant 2 (which needs OSM_CALLS>0). Deliberately a note, not a block: absence of an OSM
# call is not a provable lie, the hook sees only THIS subagent's transcript (grounding may have
# happened upstream), and many .py writes legitimately need no OSM (util/migration/test/
# __init__/__manifest__/data, or OSM simply unreachable). Blocking those would false-block real
# work and pressure the agent into emitting an unverifiable `grounded: local-source`. So: nudge,
# don't gate — the hard quality gate is verify-backend.sh/CI (behavior), not OSM-call-count.
if [[ "$PY_WRITES" -gt 0 && "$OSM_CALLS" -eq 0 && "$CLAIMS_OSM" -eq 0 && "$CLAIMS_LOCAL" -eq 0 ]]; then
    jq -cn --arg m "Grounding note: this subagent wrote backend Python (.py) but made ZERO mcp__odoo-semantic__* calls and emitted no grounding label. If the file touches ORM (models/fields/@api.depends/domain=/related=), ground it before presenting — set_active_version + model_inspect/entity_lookup to verify, then the Round-4 ORM validators + scripts/verify-backend.sh — or, if OSM is unreachable, ground against disk and label \`grounded: local-source (not OSM-indexed)\`. If the file is pure-Python with no ORM (util/migration/test/__init__/__manifest__/data), say so, so the grounding gate is satisfied. Don't leave Odoo backend code silently ungrounded.${GUIDELINES_NOTE}" \
        '{continue:true, systemMessage:$m}'
    exit 0
fi

# NOTE: the read-before-write reminder is appended to Invariants 2/3 (via $GUIDELINES_NOTE), not
# emitted as its own invariant. A standalone note would nag honest, fully-grounded subagents that
# simply did not read a guidelines file — which contradicts the "honest work passes clean"
# contract. The primary read-before-write enforcement is the agent-prompt gate; the hook only adds
# the reminder when it is ALREADY nudging for a grounding gap.

_pass
