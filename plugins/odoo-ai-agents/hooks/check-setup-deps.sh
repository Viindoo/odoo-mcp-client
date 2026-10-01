#!/usr/bin/env bash
# check-setup-deps.sh - SessionStart readiness probe for odoo-ai-agents visual stack.
# READ-ONLY: never writes, never installs, never blocks the session.
# Prints a one-block hint (<=4 lines) when deps are missing; stays silent when all is well.
# Always exits 0.
set -uo pipefail

missing=()

# (a) node >= 20
if command -v node >/dev/null 2>&1; then
  _node_major=$(node --version 2>/dev/null | sed 's/^v//' | cut -d. -f1 || echo 0)
  if [ "${_node_major:-0}" -lt 20 ] 2>/dev/null; then
    missing+=("node>=20 (found v${_node_major})")
  fi
else
  missing+=("node>=20 (not in PATH)")
fi

# (b) the Playwright Chromium pagecast launches, revision-exact. Setup step 20 records the
# `Install location:` paths it verified for the pinned playwright; this re-checks that record (no
# npx - too slow here): missing, written for another pinned version, or a location that lost its
# INSTALLATION_COMPLETE marker all mean setup must run again. Another revision's chromium-*
# directory never counts. Silent when the check itself cannot run (no python3, an error).
_plugin_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")/../scripts/lib" 2>/dev/null && pwd)"
if command -v python3 >/dev/null 2>&1 && [ -f "${_plugin_lib}/browser_mcp_servers.py" ]; then
  _pw_reason="$(python3 "${_plugin_lib}/browser_mcp_servers.py" chromium-record check 2>/dev/null)"
  case "${_pw_reason}" in
    missing|outdated|incomplete)
      missing+=("playwright-browsers (${_pw_reason} - run /odoo-ai-agents:odoo-setup browser)") ;;
  esac
fi

# (c) ffmpeg in PATH
command -v ffmpeg >/dev/null 2>&1 || missing+=("ffmpeg (not in PATH)")

# (d) chrome-devtools MCP wired in at least one CLI config.
# Claude Code itself is already wired by virtue of this plugin bundling its own
# .mcp.json (the eager chrome-devtools loads when the plugin is installed) - so a
# running Claude Code session that executes this hook is by definition wired.
# We do NOT check ~/.claude.json: step 10 intentionally never writes there to
# avoid duplicate-skip notes. We only check cross-runtime CLIs (Codex / Gemini)
# where step 10 writes the registry.
_browser_mcp_wired=true  # Claude is always wired via bundled .mcp.json
_codex_cfg="${CODEX_CONFIG:-${HOME}/.codex/config.toml}"
_gemini_cfg="${GEMINI_SETTINGS:-${HOME}/.gemini/settings.json}"
if [ -f "${_codex_cfg}" ] && ! grep -q "chrome-devtools" "${_codex_cfg}" 2>/dev/null; then
  _browser_mcp_wired=false
fi
if [ -f "${_gemini_cfg}" ] && ! grep -q "chrome-devtools" "${_gemini_cfg}" 2>/dev/null; then
  _browser_mcp_wired=false
fi

${_browser_mcp_wired} || missing+=("chrome-devtools MCP (not wired in Codex/Gemini - run setup)")

# (e) browser MCP registrations whose launch differs from what setup writes today (an older pin,
# no state-root flag, a moved state root). Read-only: scripts/lib/browser_mcp_servers.py drift
# prints "<runtime> <server>" per drifted registration and "<runtime> ?" for a config it could
# not read (drift unknown there, never "none").
_drifted=()
_unread=()
if command -v python3 >/dev/null 2>&1 && [ -f "${_plugin_lib}/browser_mcp_servers.py" ]; then
  while read -r _rt _srv; do
    [ -n "${_rt}" ] && [ -n "${_srv}" ] || continue
    if [ "${_srv}" = "?" ]; then _unread+=("${_rt}"); else _drifted+=("${_rt}:${_srv}"); fi
  done < <(python3 "${_plugin_lib}/browser_mcp_servers.py" drift 2>/dev/null || true)
fi
_join() { local out="" item; for item in "$@"; do out="${out:+${out}, }${item}"; done; printf '%s' "${out}"; }
if [ "${#_drifted[@]}" -gt 0 ]; then
  echo "i  browser MCP flags outdated ($(_join "${_drifted[@]}")) - run /odoo-ai-agents:odoo-setup browser, then restart the session." >&2
fi
if [ "${#_unread[@]}" -gt 0 ]; then
  echo "i  browser MCP flags not checked ($(_join "${_unread[@]}") config unreadable) - if captures are refused, run /odoo-ai-agents:odoo-setup browser, then restart the session." >&2
fi

# Emit the human dep hint on STDERR (visible console nudge; does not collide with the
# JSON we put on stdout for SessionStart context injection).
if [ "${#missing[@]}" -gt 0 ]; then
  _list=$(IFS=", "; echo "${missing[*]}")
  echo "i  Odoo visual stack incomplete: ${_list}." >&2
  echo "   Run /odoo-ai-agents:odoo-setup to complete the installation." >&2
fi

# SessionStart context injection: always surface the orchestration digest so the
# planning/main agent knows up front which skills spawn subagents (never forbids a
# legitimate spawn) and which require the orchestrating context. Tiny payload (~80 tokens), plugin-local,
# no machine-specific data. SSOT: docs/reference/orchestration-digest.txt (generated).
_plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
_digest_file="${_plugin_root}/docs/reference/orchestration-digest.txt"
if [ -f "${_digest_file}" ]; then
  _ctx="$(cat "${_digest_file}")"
  if command -v jq >/dev/null 2>&1; then
    jq -cn --arg ctx "${_ctx}" \
      '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $ctx}}'
  else
    # Fallback when jq is unavailable: emit as a plain console hint (no structured inject).
    printf '%s\n' "${_ctx}" >&2
  fi
fi

exit 0
