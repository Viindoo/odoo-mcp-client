#!/usr/bin/env bash
# 20-browser-deps.sh - Ensure browser automation dependencies are present.
#
# The browser MCP servers (chrome-devtools / playwright / pagecast) need:
#   - Node.js >= 20            (npx runtime for all three servers)
#   - Playwright + Chromium    (browser driver + a real browser binary)
#   - ffmpeg                   (video capture for pagecast recordings)
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if node>=20 AND chromium installed AND ffmpeg present;
#              exit 1 if anything is missing.
#   apply      Install the playwright chromium browser (no sudo). For ffmpeg
#              ONLY print OS-specific install guidance - never sudo/apt silently.
#
# HARD RULES:
#   - Never run sudo. ffmpeg is a system package; we only advise.
#   - `npx -y playwright install chromium` is user-scoped (downloads to the
#     per-user playwright cache) and is safe + idempotent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Install browser deps (Node>=20, Playwright Chromium) and verify ffmpeg"
}

# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------
_node_major() {
    command -v node >/dev/null 2>&1 || { echo "0"; return; }
    node -e 'process.stdout.write(String(process.versions.node.split(".")[0]))' 2>/dev/null || echo "0"
}

_node_ok() {
    local maj
    maj="$(_node_major)"
    [[ "$maj" =~ ^[0-9]+$ ]] && (( maj >= 20 ))
}

_chromium_ok() {
    # `playwright install --dry-run chromium` exits 0 and prints nothing
    # actionable when the browser is already installed. We instead probe the
    # cache via the CLI's own report; fall back to a non-fatal best effort.
    command -v npx >/dev/null 2>&1 || return 1
    # `playwright install chromium --dry-run` lists what WOULD be installed.
    # If chromium is already present it reports it as already installed.
    local out
    out="$(npx -y playwright install chromium --dry-run 2>/dev/null || true)"
    # When already installed, the dry-run output contains "Install location"
    # for an existing path AND does not need a download. We treat the presence
    # of a resolved browser path as installed. Conservative: also check cache.
    if printf '%s' "$out" | grep -qi "is already installed"; then
        return 0
    fi
    # Cache-dir fallback: look for a chromium-* folder in the standard caches.
    local cache
    for cache in \
        "${PLAYWRIGHT_BROWSERS_PATH:-}" \
        "$HOME/.cache/ms-playwright" \
        "$HOME/Library/Caches/ms-playwright" \
        "$HOME/AppData/Local/ms-playwright"; do
        [[ -n "$cache" && -d "$cache" ]] || continue
        if compgen -G "$cache/chromium-*" >/dev/null 2>&1; then
            return 0
        fi
    done
    return 1
}

_ffmpeg_ok() {
    command -v ffmpeg >/dev/null 2>&1
}

cmd_check() {
    local ok=0
    _node_ok      || ok=1
    _chromium_ok  || ok=1
    _ffmpeg_ok    || ok=1
    return "$ok"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
_ffmpeg_guidance() {
    echo "  ffmpeg is missing - install it manually (NO sudo will be run for you):"
    local uname_s
    uname_s="$(uname -s 2>/dev/null || echo unknown)"
    case "$uname_s" in
        Linux)
            if command -v apt-get >/dev/null 2>&1; then
                echo "    Debian/Ubuntu : sudo apt-get install ffmpeg"
            elif command -v dnf >/dev/null 2>&1; then
                echo "    Fedora        : sudo dnf install ffmpeg"
            elif command -v pacman >/dev/null 2>&1; then
                echo "    Arch          : sudo pacman -S ffmpeg"
            else
                echo "    Linux         : install 'ffmpeg' via your distro package manager"
            fi
            ;;
        Darwin)
            echo "    macOS         : brew install ffmpeg"
            ;;
        *)
            echo "    See https://ffmpeg.org/download.html for your platform"
            ;;
    esac
}

cmd_apply() {
    echo "Checking / installing browser dependencies..."

    if _node_ok; then
        echo "  ok Node >= 20 detected (v$(node -v 2>/dev/null | sed 's/^v//'))"
    else
        echo "  x Node >= 20 is REQUIRED but not found." >&2
        echo "    Install Node 20+ (nvm: 'nvm install 20', or https://nodejs.org)." >&2
        echo "    Cannot install Playwright browsers without npx. Aborting this step." >&2
        return 1
    fi

    if _chromium_ok; then
        echo "  ok Playwright Chromium already installed - skip"
    else
        echo "  Installing Playwright Chromium (npx -y playwright install chromium)..."
        npx -y playwright install chromium
        echo "  ok Playwright Chromium installed"
    fi

    if _ffmpeg_ok; then
        echo "  ok ffmpeg present ($(command -v ffmpeg))"
    else
        _ffmpeg_guidance
    fi

    echo "ok browser dependency check complete."
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "${1:-}" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply}" >&2; exit 2 ;;
esac
