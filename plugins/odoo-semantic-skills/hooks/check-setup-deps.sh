#!/usr/bin/env bash
# check-setup-deps.sh — SessionStart readiness probe for odoo-semantic-skills visual stack.
# READ-ONLY: never writes, never installs, never blocks the session.
# Prints a one-block hint (≤4 lines) when deps are missing; stays silent when all is well.
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

# (b) Playwright browser binaries installed
# A real install contains at least one browser dir (chromium-NNNN, firefox-NNNN,
# webkit-NNNN) under the cache; the actual binary sits one level deeper
# (e.g. chromium-1148/chrome-linux/chrome), so a -name "chrome" find misses it.
# Probe for the chromium-* directory itself — same logic as 20-browser-deps.sh.
_pw_ok=false
for _pw_cache in \
    "${PLAYWRIGHT_BROWSERS_PATH:-}" \
    "${HOME}/.cache/ms-playwright" \
    "${HOME}/Library/Caches/ms-playwright" \
    "${HOME}/AppData/Local/ms-playwright"; do
  [ -n "${_pw_cache}" ] && [ -d "${_pw_cache}" ] || continue
  if compgen -G "${_pw_cache}/chromium-*" >/dev/null 2>&1; then
    _pw_ok=true
    break
  fi
done
${_pw_ok} || missing+=("playwright-browsers (run: npx playwright install chromium)")

# (c) ffmpeg in PATH
command -v ffmpeg >/dev/null 2>&1 || missing+=("ffmpeg (not in PATH)")

# (d) chrome-devtools MCP wired in at least one CLI config.
# Claude Code itself is already wired by virtue of this plugin bundling its own
# .mcp.json (the three browser servers load when the plugin is installed) — so a
# running Claude Code session that executes this hook is by definition wired.
# This probe therefore only needs to confirm the cross-runtime CLIs (Codex /
# Gemini), where step 10 writes the registry. For Claude we still check its real
# MCP registry path — ~/.claude.json (key mcpServers), NOT the Claude *Desktop*
# config (~/.claude/claude_desktop_config.json), which step 10 never touches.
_browser_mcp_wired=false
_codex_cfg="${CODEX_CONFIG:-${HOME}/.codex/config.toml}"
_gemini_cfg="${GEMINI_SETTINGS:-${HOME}/.gemini/settings.json}"
_claude_cfg="${CLAUDE_CONFIG:-${HOME}/.claude.json}"
if [ -f "${_codex_cfg}" ] && grep -q "chrome-devtools" "${_codex_cfg}" 2>/dev/null; then
  _browser_mcp_wired=true
fi
if [ -f "${_gemini_cfg}" ] && grep -q "chrome-devtools" "${_gemini_cfg}" 2>/dev/null; then
  _browser_mcp_wired=true
fi
if [ -f "${_claude_cfg}" ] && grep -q "chrome-devtools" "${_claude_cfg}" 2>/dev/null; then
  _browser_mcp_wired=true
fi

${_browser_mcp_wired} || missing+=("chrome-devtools MCP (not wired in any CLI config)")

# Emit hint only when something is missing
if [ "${#missing[@]}" -gt 0 ]; then
  _list=$(IFS=", "; echo "${missing[*]}")
  echo "i  Odoo visual stack incomplete: ${_list}."
  echo "   Run /odoo-semantic-skills:setup to complete the installation."
fi

exit 0
