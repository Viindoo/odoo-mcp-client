#!/usr/bin/env bash
# detect-intent.sh - UserPromptSubmit hook: lightweight Odoo/business intent detector.
# READ-ONLY: no LLM, no writes, no blocking. Emits hookSpecificOutput.additionalContext
# when a vague/multi-fragment Odoo or business prompt is detected; stays silent otherwise.
# Always exits 0 - invisible to user even when it emits context.
set -uo pipefail

# --- Read stdin JSON ---
_input=$(cat)

# Extract .prompt (first try jq; fall back to grep/sed like check-setup-deps.sh style)
if command -v jq >/dev/null 2>&1; then
  _prompt=$(printf '%s' "${_input}" | jq -r '.prompt // ""' 2>/dev/null || echo "")
  _mode=$(printf '%s' "${_input}" | jq -r '.permission_mode // ""' 2>/dev/null || echo "")
else
  # Minimal grep/sed fallback - handles simple single-line JSON values
  _prompt=$(printf '%s' "${_input}" | grep -o '"prompt"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | sed 's/"prompt"[[:space:]]*:[[:space:]]*"//;s/"$//' || echo "")
  _mode=$(printf '%s' "${_input}" | grep -o '"permission_mode"[[:space:]]*:[[:space:]]*"[^"]*"' \
    | sed 's/"permission_mode"[[:space:]]*:[[:space:]]*"//;s/"$//' || echo "")
fi

# --- Guard: slash command → emit nothing, let it run ---
case "${_prompt}" in
  /*)
    exit 0
    ;;
esac

# --- Guard: empty prompt ---
if [ -z "${_prompt}" ]; then
  exit 0
fi

# --- Domain classification via 9-bucket keyword scan (no LLM, ~0ms) ---
# Internal buckets stay finer-grained than the emitted vocabulary (upgrade vs engineering,
# visual-UI vs engineering) so the OSM/frontend hint routing below can still distinguish them;
# `_domain_enum` (computed once classification is done) maps each bucket onto the
# workflows/_schema.md `domain` enum (SSOT) - the ONLY vocabulary that reaches the emitted
# `domain: ...` text (V-33 - the old buckets matched neither the README table nor the enum). The
# README persona table's "Domain" column cross-references the same enum.
_domain=""

_p_lower=$(printf '%s' "${_prompt}" | tr '[:upper:]' '[:lower:]')

# Word-boundary keyword match (space/punct-delimited alternations) - NOT a bare substring glob.
# `case *ui*)` used to match "req**ui**rements" and `*view*` matched "re**view**" (V-11). Left
# boundary is ALWAYS required (start-of-word) - that alone kills every mid-word embedding while
# still catching common inflections (upgrade/upgraded/upgrading) via the open right side. Pass
# "full" as $2 for keywords that are ALSO genuine PREFIXES of ordinary English words
# (doc->doctor, win->window, plan->planet, design->designate, copy->copyright, seo->Seoul,
# brief->briefly, objective->objectively, style->stylish, qa->Qatar) - those close both
# boundaries and enumerate the desired inflections explicitly instead of an open stem.
_wb() {
  if [ "${2:-}" = "full" ]; then
    printf '%s' "${_p_lower}" | grep -Eq "(^|[^a-z0-9])(${1})([^a-z0-9]|\$)"
  else
    printf '%s' "${_p_lower}" | grep -Eq "(^|[^a-z0-9])(${1})"
  fi
}

# Primary Odoo/ERP anchor - must be present or one of the domain buckets must match.
# NOT the generic `_wb`: its left boundary `[^a-z0-9]` treats the hyphen in an explicit negation
# like "non-odoo" as a word start, so `_wb` would false-anchor on a prompt that says the work is
# NOT Odoo. The dedicated boundary below allows start-of-string, a non-alnum/non-hyphen char (space,
# punctuation), or an OPTIONAL leading hyphen only when that hyphen is itself preceded by an allowed
# boundary - so a letter/digit-then-hyphen prefix ("non-odoo", "anti-odoo", "x-odoo") does NOT fire.
_odoo_anchor=false
if printf '%s' "${_p_lower}" | grep -Eq "(^|[^a-z0-9-])-?(odoo|viindoo|erp|openerp)"; then
  _odoo_anchor=true
fi

# 9-domain keyword scan
# NOTE: upgrade/migrate/migration checked FIRST to avoid being shadowed by the
# engineering bucket (which previously matched *upgrade* and *migration* before
# the upgrade bucket could fire).
if _wb 'upgrade|migrate|migration|backport|breaking|deprecat'; then
  _domain="upgrade"
fi
if [ -z "${_domain}" ] && _wb 'module|model|computed|onchange|inherit|controller|v16|v17|v18|v19|version'; then
  _domain="engineering"
fi
if [ -z "${_domain}" ]; then
  if _wb 'sale|deal|crm|lead|proposal|quotation|customer|pipeline|opportunity' \
     || _wb 'win|wins|winning|won' full; then
    _domain="sales"
  fi
fi
if [ -z "${_domain}" ]; then
  if _wb 'marketing|campaign|email|social|landing|content|blog' \
     || _wb 'seo' full; then
    _domain="marketing"
  fi
fi
if [ -z "${_domain}" ]; then
  if _wb 'strategy|roadmap|decision' \
     || _wb 'okr|okrs' full \
     || _wb 'brief|briefs|briefing|briefings' full \
     || _wb 'plan|plans|planned|planning' full \
     || _wb 'objective|objectives' full \
     || _wb 'kpi|kpis' full; then
    _domain="strategy"
  fi
fi
if [ -z "${_domain}" ]; then
  if _wb 'frontend|visual|screenshot|regression|view' \
     || _wb 'ui' full \
     || _wb 'ux' full \
     || _wb 'css' full \
     || _wb 'qweb' full \
     || _wb 'design|designs|designed|designing' full \
     || _wb 'style|styles|styling|stylesheet|stylesheets' full; then
    _domain="visual-UI"
  fi
fi
if [ -z "${_domain}" ]; then
  if _wb 'onboard|setup|install|configure' \
     || printf '%s' "${_p_lower}" | grep -Eq '(^|[^a-z0-9])first[[:space:]]+time' \
     || printf '%s' "${_p_lower}" | grep -Eq '(^|[^a-z0-9])getting[[:space:]]+start' \
     || printf '%s' "${_p_lower}" | grep -Eq '(^|[^a-z0-9])new[[:space:]]+user'; then
    _domain="onboarding"
  fi
fi
if [ -z "${_domain}" ]; then
  if _wb 'document|write|draft|translate|localiz' \
     || _wb 'docs|documents|documentation' full \
     || _wb 'copy|copies|copied|copying' full; then
    _domain="content"
  fi
fi
if [ -z "${_domain}" ]; then
  if _wb 'test|bug|issue|support|ticket|error|debug|fail' \
     || _wb 'qa' full; then
    _domain="QA-support"
  fi
fi

# Require either a domain-bucket hit OR an Odoo anchor before proceeding at all. Odoo-SPECIFIC
# hints (OSM tool reminder, frontend-specialist routing below) are gated SEPARATELY on
# `_odoo_anchor=true` (V-11) - a domain hit alone (e.g. a genuine non-Odoo "strategy" or
# "marketing" business prompt) can still reach the general vague-dispatch hint, but never the
# Odoo-tool-calling or frontend-agent-naming hints without a real Odoo/Viindoo anchor.
if [ -z "${_domain}" ] && [ "${_odoo_anchor}" = "false" ]; then
  exit 0
fi

# If odoo anchor but no domain, label generic
if [ -z "${_domain}" ]; then
  _domain="general"
fi

# Map the internal bucket to the workflows/_schema.md `domain` enum (SSOT):
# engineering|sales|presales|marketing|strategy|qa|support|content|consultant. This
# keyword-scan hook never has a reliable signal for "presales" specifically (that distinction
# needs deal-stage context this hook does not have), so it is not a target bucket here.
case "${_domain}" in
  upgrade|visual-UI) _domain_enum="engineering" ;;
  onboarding|QA-support) _domain_enum="support" ;;
  general) _domain_enum="consultant" ;;
  *) _domain_enum="${_domain}" ;;
esac

# --- OSM-availability probe ---
# Grep for "odoo-semantic" in the Claude config file (same pattern as check-setup-deps.sh
# uses for chrome-devtools). Safe when the file is absent: grep returns non-zero, no error.
_osm_wired=false
_claude_cfg="${CLAUDE_CONFIG:-$HOME/.claude.json}"
if [ -f "${_claude_cfg}" ] && grep -q "odoo-semantic" "${_claude_cfg}" 2>/dev/null; then
  _osm_wired=true
fi

# --- Vagueness heuristic: short prompt / multi-fragment / no strong action verb ---
# Word count proxy via wc -w
_word_count=$(printf '%s' "${_prompt}" | wc -w | tr -d ' ')

# Action-verb present check (engineering/concrete single-step phrases). Same word-boundary
# discipline as the domain-bucket scan above (V-11 class - a bare substring glob previously let
# *diff* match inside "different", *list* match inside "listen", *show* match inside "shower",
# *check* match inside "checkup"/"checkers", *audit* match inside "auditorium", *fix* match
# inside "fixture", *run* match inside "rung").
_has_action=false
if _wb 'write|create|generate|review|debug|deploy|compare|find|analyze|report' \
   || _wb 'fix|fixes|fixed|fixing' full \
   || _wb 'run|runs|running|ran' full \
   || _wb 'diff|diffs' full \
   || _wb 'show|shows|showed|showing' full \
   || _wb 'list|lists|listed|listing' full \
   || _wb 'check|checks|checked|checking' full \
   || _wb 'audit|audits|audited|auditing' full; then
  _has_action=true
fi

# Lookup/introspection intent - question is about indexed STRUCTURE (which
# modules/repos/models a profile or version contains), NOT code-gen. The
# indexed answer lives in odoo-semantic (profile_inspect / describe_module /
# model_inspect), never in the vault. EN + VI phrasings. Same word-boundary discipline (V-11
# class) - *repo* previously matched inside "report" (a keyword in the action-verb list above).
_is_lookup=false
if _wb 'module|profile|inventory|composition|compose' \
   || _wb 'repo|repos|repository|repositories' full \
   || _wb 'gồm|có gì|module nào|repo nào|những gì|có bao nhiêu'; then
  _is_lookup=true
fi

# Consider vague when: short (<= 12 words) OR no action verb detected
_is_vague=false
if [ "${_word_count}" -le 12 ] 2>/dev/null || [ "${_has_action}" = "false" ]; then
  _is_vague=true
fi

# --- OSM reminder block (emitted BEFORE any early-exit) ---
# Emitted when odoo-semantic MCP is wired AND domain is engineering/upgrade/visual-UI.
# Fires regardless of vague/specific - specific prompts need it most.
_osm_context=""
case "${_domain}" in
  engineering|upgrade|visual-UI)
    # V-11: an Odoo-specific tool-calling hint must never fire without a real Odoo/Viindoo
    # anchor - a domain-bucket match alone (e.g. a non-Odoo "visual design" or "version" prompt)
    # is not proof this is an Odoo task.
    if [ "${_odoo_anchor}" = "true" ] && [ "${_osm_wired}" = "true" ]; then
      _osm_r1="[OSM] odoo-semantic index is AVAILABLE - before generating or editing Odoo code, call mcp__odoo-semantic__set_active_version then model_inspect/entity_lookup; do NOT code from memory. If a tool errors at call time, fall back to disk-grounded mode (Read/Grep the addons source yourself), not to asking a human to paste."
      _osm_r2="[Tip] For an engineering task, planning enters Plan Mode for you before any file is changed."
      _osm_context="${_osm_r1}\n${_osm_r2}"
    fi
    ;;
esac

# --- OSM lookup hint (composition/introspection) ---
# Fires on Odoo/Viindoo anchor + lookup intent, INDEPENDENT of _domain - so a
# "general"-domain Viindoo question (e.g. "viindoo 17 gồm những gì") still gets
# routed to the index instead of the vault. Names the exact lookup tools, which
# may be ToolSearch-deferred (only their name in context) - this hint is the
# in-context pointer that survives deferral.
if [ "${_osm_wired}" = "true" ] && [ "${_odoo_anchor}" = "true" ] && [ "${_is_lookup}" = "true" ]; then
  _osm_lk="[OSM-lookup] This is a STRUCTURE-lookup over indexed data (module/repo/profile/version composition) - use mcp__odoo-semantic__profile_inspect (composition of one profile, e.g. standard_viindoo_17 / odoo_17: repos + module count + ancestor chain), describe_module (what one module does), or model_inspect (fields/methods of one model). Do NOT search the vault for data already indexed in odoo-semantic."
  _osm_context="${_osm_context:+${_osm_context}\n}${_osm_lk}"
fi

# --- Stack-aware routing hints (named specialists, so a JS/OWL or full-stack task never
# silently skips the frontend specialists). Appended to whatever OSM context exists. ---
case "${_domain}" in
  visual-UI)
    # V-11: gated on the Odoo anchor too (previously unconditional) - naming
    # odoo-coding/odoo-debug/odoo-ui-review is wrong for a domain-bucket match with no actual
    # Odoo/Viindoo anchor in the prompt (e.g. a non-Odoo "review this contract" false match).
    if [ "${_odoo_anchor}" = "true" ]; then
      _fe_hint="[Frontend/UI specialists] JS/OWL/SCSS/QWeb work → odoo-coding (write, its frontend leg); odoo-debug (runtime render/console errors); odoo-ui-review (rate a working screen); odoo-visual-regression (before/after diff). Theme/token fidelity → see skills/_shared/odoo-frontend-fidelity.md (build theme-correct, never hardcode hex / self-reference a CSS var)."
      _osm_context="${_osm_context:+${_osm_context}\n}${_fe_hint}"
    fi
    ;;
  engineering)
    # Only when OSM context already fired (i.e. anchor true + OSM wired) - avoids noising every
    # prompt; the anchor check here is redundant with the OSM block above but kept explicit so
    # this branch's own invariant (never fire without an anchor) does not depend on reading
    # the block above.
    if [ "${_odoo_anchor}" = "true" ] && [ -n "${_osm_context}" ]; then
      _fe_hint="[Stack check] If the change touches JS/OWL/QWeb or an asset bundle, odoo-coding covers it (its frontend leg) alongside the backend in the same pass - full-stack is one skill, no separate frontend step needed."
      _osm_context="${_osm_context}\n${_fe_hint}"
    fi
    ;;
esac

# If intent is specific (long + has action verb) AND no OSM context to emit → exit early
if [ "${_is_vague}" = "false" ] && [ -z "${_osm_context}" ]; then
  exit 0
fi

# --- Emit additionalContext (hookSpecificOutput JSON) ---
# The hint is NL-dispatch friendly: names outcomes/domains, NOT tool names.
# Newlines inside the JSON string MUST be the escaped sequence \n (two chars),
# not a literal control character - a raw newline inside a JSON string is invalid
# JSON and Claude Code silently drops the hook. Build the message with literal
# "\n" separators and emit valid JSON (prefer jq; safe printf fallback).

# Build context: OSM block (if any) + vague-dispatch hint (if vague)
_context=""
if [ -n "${_osm_context}" ]; then
  _context="${_osm_context}"
fi

if [ "${_is_vague}" = "true" ]; then
  _hint="Business/Odoo intent detected (domain: ${_domain_enum})."
  _line2="If the goal is still broad or you want to explore options first, the odoo-intake front door can brainstorm approaches and route to the right specialist."
  _line3="If the intent is already specific and single-step, the matching specialist will fire directly - no extra step needed."
  _nl_hint="${_hint}\n${_line2}\n${_line3}"
  if [ -n "${_context}" ]; then
    _context="${_context}\n${_nl_hint}"
  else
    _context="${_nl_hint}"
  fi
fi

# --- Language-mirroring reminder (SSOT: snippets/language-mirroring.md) ---
# Non-ASCII letters in the prompt => the user is not writing plain English.
# Remind the main agent to mirror that language in ALL chat-facing output
# (gates, proposals, questions, summaries, relays of subagent results).
if printf '%s' "${_prompt}" | LC_ALL=C grep -q '[^ -~]'; then
  _lang_line="[Language] The user's prompt is not plain English. Mirror the USER'S language in every chat output - gates, proposals, plans, clarifying questions, summaries, and relays of subagent results. Keep code, identifiers, file paths, tool/skill names, URLs, and the literal reply keywords (approve / refine / cancel / yes) verbatim; explain unavoidable technical terms in plain words in the user's language on first use. SSOT: plugin snippets/language-mirroring.md"
  if [ -n "${_context}" ]; then
    _context="${_context}\n${_lang_line}"
  else
    _context="${_lang_line}"
  fi
fi

if command -v jq >/dev/null 2>&1; then
  # jq emits a properly escaped JSON string (handles the \n + any quoting).
  jq -cn --arg ctx "$(printf '%b' "${_context}")" \
    '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $ctx}}'
else
  # Fallback: the \n stay as the two-character escape sequence inside the JSON
  # string (valid JSON). No user-controlled text is interpolated, so no escaping
  # of the static hint is required.
  printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":"%s"}}\n' \
    "${_context}"
fi

exit 0
