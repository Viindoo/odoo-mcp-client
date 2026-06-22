#!/usr/bin/env bash
# ensure-ethos-import.sh - SessionStart idempotent inject of a sentinel-bounded
# @import block for ODOO-AI-ETHOS.md into the user's ~/.claude/CLAUDE.md.
#
# WHY a hook (not just docs): CLAUDE.md is read at session start; the @import
# gives every main agent and custom sub-agent the plugin's curated principles
# file without manual copy-paste. First run appends the block AND bridges the
# content into the current session via additionalContext (because CLAUDE.md was
# already read before this hook ran). Subsequent runs are no-ops.
#
# Contract: idempotent, never blocks the session, always exits 0.
#   - Escape hatch: export ODOO_AI_NO_ETHOS_IMPORT=1 to disable (dedicated var;
#     separate from ODOO_AI_NO_AUTO_PERMS so opting out of browser permissions
#     does not silently suppress ETHOS loading).
#   - Honours CLAUDE_CONFIG_DIR for tests / non-default homes.
set -uo pipefail

# Dedicated opt-out var - separate from browser-permission opt-out.
if [ "${ODOO_AI_NO_ETHOS_IMPORT:-0}" = "1" ]; then
  exit 0
fi

_plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
P="${_plugin_root}/ODOO-AI-ETHOS.md"

# Source file absent (other agent hasn't written it yet) -> stay silent, do nothing.
[ -f "${P}" ] || exit 0

# Target: honour CLAUDE_CONFIG_DIR env override (test seam).
_cfg_dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
_md="${_cfg_dir}/CLAUDE.md"
mkdir -p "${_cfg_dir}"
# Create CLAUDE.md if missing.
[ -f "${_md}" ] || : > "${_md}"

# Sentinel marker strings (fixed; used with grep -F for literal matching).
_BEGIN='<!-- BEGIN odoo-ai-agents ETHOS import (managed by ensure-ethos-import.sh - do not edit inside) -->'
_END='<!-- END odoo-ai-agents ETHOS import -->'
_import_line="@${P}"

# ---------------------------------------------------------------------------
# Helper: append one fresh block (BEGIN + import + END) to _md.
# Precedes with a blank line when the file is non-empty and does not end with one.
# ---------------------------------------------------------------------------
_append_block() {
  if [ -s "${_md}" ]; then
    _last=$(tail -c 1 "${_md}" | od -An -tx1 | tr -d ' \n')
    if [ "${_last}" != "0a" ]; then
      printf '\n' >> "${_md}"
    fi
    printf '\n' >> "${_md}"
  fi
  {
    printf '%s\n' "${_BEGIN}"
    printf '%s\n' "${_import_line}"
    printf '%s\n' "${_END}"
  } >> "${_md}"
}

# ---------------------------------------------------------------------------
# Symlink-preserving in-place rewrite: writes through symlinks to their target.
# Takes a tmp file path; moves its content into _md, then removes the tmp file.
# ---------------------------------------------------------------------------
_replace_through_symlink() {
  local _tmp="$1"
  cat "${_tmp}" > "${_md}" && rm -f "${_tmp}"
}

# ---------------------------------------------------------------------------
# Classify the current state of _md into one of four cases and act accordingly.
# _added=1 only for a true first-install (ABSENT case) to gate the bridge.
# ---------------------------------------------------------------------------
_begin_count=$(grep -cF "${_BEGIN}" "${_md}" 2>/dev/null || true)
_end_count=$(grep -cF "${_END}" "${_md}" 2>/dev/null || true)

_added=0

if [ "${_begin_count}" -eq 0 ] && [ "${_end_count}" -eq 0 ]; then
  # --- ABSENT: no block anywhere -> append a fresh one, set bridge flag ---
  _append_block
  _added=1

elif [ "${_begin_count}" -eq 1 ] && [ "${_end_count}" -eq 1 ]; then
  # --- ONE OF EACH: check ordering to determine well-formed vs inverted ---
  _begin_line=$(grep -nF "${_BEGIN}" "${_md}" | head -1 | cut -d: -f1)
  _end_line=$(grep -nF "${_END}" "${_md}" | head -1 | cut -d: -f1)

  if [ "${_begin_line}" -lt "${_end_line}" ]; then
    # --- WELL-FORMED: read current import line between markers ---
    _inner_line=$(( _begin_line + 1 ))
    _current_import=""
    if [ "${_inner_line}" -lt "${_end_line}" ]; then
      _current_import=$(awk "NR==${_inner_line}{print; exit}" "${_md}")
    fi

    if [ "${_current_import}" = "${_import_line}" ]; then
      # Already exactly right -> no-op (file stays byte-identical).
      :
    else
      # Stale/relocated path -> range-delete block, re-append correct one.
      _tmp=$(mktemp)
      awk -v b="${_begin_line}" -v e="${_end_line}" \
        'NR < b || NR > e' "${_md}" > "${_tmp}"
      _replace_through_symlink "${_tmp}"
      _append_block
      # Not first install -> _added stays 0, no bridge.
    fi
  else
    # Inverted sentinels (END before BEGIN) -> fall through to MALFORMED sanitizer.
    _begin_count=99
  fi
fi

# MALFORMED / SANITIZE: catches inverted sentinels, duplicate markers, or any
# state that did not resolve cleanly above. Removes every line that is our
# BEGIN sentinel, END sentinel, or our import pattern; then appends one fresh
# block. Never touches user content outside those exact lines.
if [ "${_begin_count}" -ne 0 ] && \
   { [ "${_begin_count}" -ne 1 ] || [ "${_end_count}" -ne 1 ] || \
     [ "${_begin_count}" -eq 99 ]; }; then
  _tmp=$(mktemp)
  grep -vxF "${_BEGIN}" "${_md}" | \
    grep -vxF "${_END}" | \
    grep -vE "^@.*/ODOO-AI-ETHOS\.md$" > "${_tmp}" || true
  _replace_through_symlink "${_tmp}"
  _append_block
  # Repair, not first install -> _added stays 0, no bridge.
fi

# ---------------------------------------------------------------------------
# Install-session bridge: ONLY on first add, emit ETHOS content as additionalContext
# so the current session gets coverage (CLAUDE.md was already parsed before this hook).
# ---------------------------------------------------------------------------
if [ "${_added}" -eq 1 ]; then
  _ctx="$(cat "${P}")"
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg ctx "${_ctx}" \
      '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
  else
    # Fallback when jq is unavailable: emit as a plain console hint (no structured inject).
    printf '%s\n' "${_ctx}" >&2
  fi
  # Loud first-add notice so the user knows what changed and how to opt out.
  echo "i  odoo-ai-agents: added an @import of ODOO-AI-ETHOS.md to ${_md}. These principles now load in ALL your Claude Code projects. Opt out: set ODOO_AI_NO_ETHOS_IMPORT=1. Undo: delete the marked block in ${_md}." >&2
fi

echo "i  odoo-ai-agents: ensured ETHOS @import in ${_md}" >&2

exit 0
