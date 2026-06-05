#!/usr/bin/env bash
# detect-intent.sh — UserPromptSubmit hook: lightweight Odoo/business intent detector.
# READ-ONLY: no LLM, no writes, no blocking. Emits hookSpecificOutput.additionalContext
# when a vague/multi-fragment Odoo or business prompt is detected; stays silent otherwise.
# Always exits 0 — invisible to user even when it emits context.
set -uo pipefail

# --- Read stdin JSON ---
_input=$(cat)

# Extract .prompt (first try jq; fall back to grep/sed like check-setup-deps.sh style)
if command -v jq >/dev/null 2>&1; then
  _prompt=$(printf '%s' "${_input}" | jq -r '.prompt // ""' 2>/dev/null || echo "")
  _mode=$(printf '%s' "${_input}" | jq -r '.permission_mode // ""' 2>/dev/null || echo "")
else
  # Minimal grep/sed fallback — handles simple single-line JSON values
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
# Buckets match the README 9-persona taxonomy used across the plugin.
_domain=""

_p_lower=$(printf '%s' "${_prompt}" | tr '[:upper:]' '[:lower:]')

# Primary Odoo/ERP anchor — must be present or one of the domain buckets must match
_odoo_anchor=false
case "${_p_lower}" in
  *odoo*|*viindoo*|*erp*|*openerp*)
    _odoo_anchor=true ;;
esac

# 9-domain keyword scan
# NOTE: upgrade/migrate/migration checked FIRST to avoid being shadowed by the
# engineering bucket (which previously matched *upgrade* and *migration* before
# the upgrade bucket could fire).
case "${_p_lower}" in
  *upgrade*|*migrate*|*migration*|*backport*|*breaking*|*deprecat*)
    _domain="upgrade" ;;
esac
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *module*|*model*|*computed*|*onchange*|*inherit*|*controller*|*v16*|*v17*|*v18*|*v19*|*version*)
      _domain="engineering" ;;
  esac
fi
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *sale*|*deal*|*crm*|*lead*|*proposal*|*quotation*|*customer*|*pipeline*|*win*|*opportunity*)
      _domain="sales" ;;
  esac
fi
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *marketing*|*campaign*|*email*|*social*|*landing*|*content*|*seo*|*blog*)
      _domain="marketing" ;;
  esac
fi
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *strategy*|*okr*|*roadmap*|*decision*|*brief*|*plan*|*objective*|*kpi*)
      _domain="strategy" ;;
  esac
fi
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *ui*|*ux*|*view*|*frontend*|*visual*|*design*|*screenshot*|*regression*|*style*|*css*|*qweb*)
      _domain="visual-UI" ;;
  esac
fi
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *onboard*|*setup*|*install*|*configure*|*first*time*|*getting*start*|*new*user*)
      _domain="onboarding" ;;
  esac
fi
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *document*|*doc*|*write*|*draft*|*content*|*translate*|*localiz*|*copy*)
      _domain="content" ;;
  esac
fi
if [ -z "${_domain}" ]; then
  case "${_p_lower}" in
    *test*|*qa*|*bug*|*issue*|*support*|*ticket*|*error*|*debug*|*fail*)
      _domain="QA-support" ;;
  esac
fi

# Require either Odoo anchor OR a domain hit before proceeding
if [ -z "${_domain}" ] && [ "${_odoo_anchor}" = "false" ]; then
  exit 0
fi

# If odoo anchor but no domain, label generic
if [ -z "${_domain}" ]; then
  _domain="general"
fi

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

# Action-verb present check (engineering/concrete single-step phrases)
_has_action=false
case "${_p_lower}" in
  *write*|*create*|*generate*|*fix*|*review*|*debug*|*run*|*deploy*|*diff*|*compare*|*show*|*list*|*check*|*find*|*analyze*|*audit*|*report*)
    _has_action=true ;;
esac

# Consider vague when: short (<= 12 words) OR no action verb detected
_is_vague=false
if [ "${_word_count}" -le 12 ] 2>/dev/null || [ "${_has_action}" = "false" ]; then
  _is_vague=true
fi

# --- OSM reminder block (emitted BEFORE any early-exit) ---
# Emitted when odoo-semantic MCP is wired AND domain is engineering/upgrade/visual-UI.
# Fires regardless of vague/specific — specific prompts need it most.
_osm_context=""
case "${_domain}" in
  engineering|upgrade|visual-UI)
    if [ "${_osm_wired}" = "true" ]; then
      _osm_r1="[OSM] odoo-semantic index is AVAILABLE - before generating or editing Odoo code, call mcp__odoo-semantic__set_active_version then model_inspect/entity_lookup; do NOT code from memory. If a tool errors at call time, fall back to disk-grounded mode (Read/Grep the addons source yourself), not to asking a human to paste."
      _osm_r2="[Tip] Type /plan or press Shift+Tab to enter Plan Mode and review the full plan before any file is changed."
      _osm_context="${_osm_r1}\n${_osm_r2}"
    fi
    ;;
esac

# --- Stack-aware routing hints (named specialists, so a JS/OWL or full-stack task never
# silently skips the frontend specialists). Appended to whatever OSM context exists. ---
case "${_domain}" in
  visual-UI)
    _fe_hint="[Frontend/UI specialists] JS/OWL/SCSS/QWeb work → odoo-frontend-coding (write); odoo-ui-debug (runtime render/console errors); odoo-ui-reviewer (rate a working screen); odoo-visual-regression (before/after diff). Theme/token fidelity → see skills/_shared/odoo-frontend-fidelity.md (build theme-correct, never hardcode hex / self-reference a CSS var)."
    _osm_context="${_osm_context:+${_osm_context}\n}${_fe_hint}"
    ;;
  engineering)
    # Only when OSM context already fired (i.e. OSM wired) — avoids noising every prompt.
    if [ -n "${_osm_context}" ]; then
      _fe_hint="[Stack check] If the change touches JS/OWL/QWeb or an asset bundle, also engage odoo-frontend-coding — backend (odoo-coder) does not cover frontend. Full-stack tasks need both."
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
# not a literal control character — a raw newline inside a JSON string is invalid
# JSON and Claude Code silently drops the hook. Build the message with literal
# "\n" separators and emit valid JSON (prefer jq; safe printf fallback).

# Build context: OSM block (if any) + vague-dispatch hint (if vague)
_context=""
if [ -n "${_osm_context}" ]; then
  _context="${_osm_context}"
fi

if [ "${_is_vague}" = "true" ]; then
  _hint="Business/Odoo intent detected (domain: ${_domain})."
  _line2="If the goal is still broad or you want to explore options first, the intake front door can brainstorm approaches and route to the right specialist."
  _line3="If the intent is already specific and single-step, the matching specialist will fire directly - no extra step needed."
  _nl_hint="${_hint}\n${_line2}\n${_line3}"
  if [ -n "${_context}" ]; then
    _context="${_context}\n${_nl_hint}"
  else
    _context="${_nl_hint}"
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
