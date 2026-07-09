#!/usr/bin/env bash
# browser-mcp-servers.sh - SSOT for the browser MCP families' npx invocation.
#
# The plugin ships SIX browser MCP server families: three backends
# (chrome-devtools, playwright, pagecast), each with a headless default and a
# `-headed` variant. Exactly ONE is EAGER (bundled in the plugin's .mcp.json and
# therefore auto-loaded by Claude on install, and mirrored into the Codex/Gemini
# bundle manifests by generator/gen_mcp_manifests.py): the headless
# `chrome-devtools`. The other FIVE are OPT-IN - wired on demand by the
# odoo-setup steps only when the user opts into the visual/doc workflow, so a
# plain session never launches six npx browser processes it does not need.
#
# This file is the single source of truth for each family's `npx` package + flags.
# It is SOURCED (not executed) by:
#   - setup-steps/10-browser-mcp.sh        (Codex/Gemini opt-in wiring)
#   - setup-steps/12-browser-mcp-optin.sh  (Claude user-scope opt-in wiring)
# The eager chrome-devtools line MUST stay byte-for-byte in sync with the plugin's
# bundled .mcp.json (JSON cannot source this shell file); a mismatch is a bug.
#
# Versions are PINNED to the current published MAJOR (never `@latest`) so a
# session is reproducible. Override any pin via env for testing / staging.
# (0.x packages have no stable major yet - `@0` pins the 0.x line as published.)

BROWSER_MCP_CHROME_PIN="${BROWSER_MCP_CHROME_PIN:-chrome-devtools-mcp@1}"
BROWSER_MCP_PLAYWRIGHT_PIN="${BROWSER_MCP_PLAYWRIGHT_PIN:-@playwright/mcp@0}"
BROWSER_MCP_PAGECAST_PIN="${BROWSER_MCP_PAGECAST_PIN:-@mcpware/pagecast@0}"

# The one eager family (also in .mcp.json) and the five opt-in families.
BROWSER_MCP_EAGER_SERVER="chrome-devtools"
BROWSER_MCP_ALL_SERVERS=(chrome-devtools chrome-devtools-headed playwright playwright-headed pagecast pagecast-headed)
BROWSER_MCP_OPTIN_SERVERS=(chrome-devtools-headed playwright playwright-headed pagecast pagecast-headed)

# browser_mcp_npx_args <server> - print, one per line, the npx args (after `-y`)
# for a family: the pinned package first, then its flags. Headed variants drop
# `--headless`; chrome-devtools/playwright pass `--isolated` (private profile per
# launch -> concurrent-session safe); pagecast isolates per-session internally
# and takes no `--isolated`.
browser_mcp_npx_args() {
    case "$1" in
        chrome-devtools)        printf '%s\n' "$BROWSER_MCP_CHROME_PIN" "--headless" "--isolated" ;;
        chrome-devtools-headed) printf '%s\n' "$BROWSER_MCP_CHROME_PIN" "--isolated" ;;
        playwright)             printf '%s\n' "$BROWSER_MCP_PLAYWRIGHT_PIN" "--caps=devtools" "--headless" "--isolated" ;;
        playwright-headed)      printf '%s\n' "$BROWSER_MCP_PLAYWRIGHT_PIN" "--caps=devtools" "--isolated" ;;
        pagecast)               printf '%s\n' "$BROWSER_MCP_PAGECAST_PIN" "--headless" ;;
        pagecast-headed)        printf '%s\n' "$BROWSER_MCP_PAGECAST_PIN" ;;
        *) return 1 ;;
    esac
}
