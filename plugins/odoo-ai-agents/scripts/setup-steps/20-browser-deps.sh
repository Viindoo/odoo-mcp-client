#!/usr/bin/env bash
# 20-browser-deps.sh - Ensure browser automation dependencies are present.
#
# The browser MCP servers (chrome-devtools / playwright / pagecast) need:
#   - Node.js >= 20            (npx runtime for all three servers)
#   - Playwright + Chromium    (browser driver + a real browser binary)
#   - Chromium system libs     (libnss3 / libgbm / fonts / ... on Linux)
#   - ffmpeg                   (video/GIF capture for pagecast recordings)
#
# Playwright is pinned via PLAYWRIGHT_PIN (default below). The default is the
# first release that supports current Ubuntu while still running on older
# Linux / macOS / Windows. The pagecast server resolves to the same Playwright
# minor and therefore shares this Chromium build + system libs, so installing
# them here covers pagecast as well.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if node>=20 AND chromium installed AND (on apt-based
#              Linux) chromium system libs present AND ffmpeg present;
#              exit 1 if anything is missing.
#   apply      Install the pinned Playwright Chromium browser, and on apt-based
#              Linux also install its system libraries - automatically only when
#              passwordless sudo is available, otherwise print the exact command
#              to run. For ffmpeg ONLY print OS-specific guidance.
#
# HARD RULES:
#   - Never run sudo silently. System libs run via `playwright install-deps`
#     ONLY when `sudo -n` (passwordless) succeeds; otherwise we advise the
#     exact command. ffmpeg is always advise-only.
#   - `npx -y playwright@<pin> install chromium` is user-scoped (downloads to
#     the per-user playwright cache) and is safe + idempotent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Pinned Playwright version (single source of truth, env-overridable so users
# and CI can pick a different release without editing this script).
PW_PIN="${PLAYWRIGHT_PIN:-1.61.0}"

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Install browser deps (Node>=20, pinned Playwright Chromium + system libs on apt Linux) and verify ffmpeg"
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

_is_apt_linux() {
    [[ "$(uname -s 2>/dev/null || echo unknown)" == "Linux" ]] && command -v apt-get >/dev/null 2>&1
}

_can_sudo_nopasswd() {
    command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null
}

_chromium_ok() {
    # `playwright install chromium --dry-run` lists what WOULD be installed.
    # If chromium is already present it reports it as already installed. The
    # version is pinned so the probe matches what `apply` would install.
    command -v npx >/dev/null 2>&1 || return 1
    local out
    out="$(npx -y "playwright@${PW_PIN}" install chromium --dry-run 2>/dev/null || true)"
    # here-string (not `printf | grep`) to avoid the pipefail/SIGPIPE trap.
    if grep -qi "is already installed" <<<"$out"; then
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

# Best-effort probe that Chromium's shared system libraries are present.
# Only meaningful on apt-based Linux; everywhere else returns 0 (not
# applicable) so the check does not falsely fail on macOS/Windows/non-apt.
_system_deps_ok() {
    _is_apt_linux || return 0
    command -v ldconfig >/dev/null 2>&1 || return 0
    # Match real sonames as printed by ldconfig, not Debian package names:
    # e.g. package libasound2 ships libasound.so.2 (a "libasound2" substring
    # would never match). libgbm.so avoids the unrelated libnvidia-egl-gbm.
    # Use a bash glob (case) instead of `printf | grep -q`: under `pipefail`,
    # grep -q closes the pipe early on a match and printf dies with SIGPIPE,
    # making the whole pipeline non-zero and falsely reporting a lib missing.
    local lib known
    known="$(ldconfig -p 2>/dev/null || true)"
    for lib in libnss3.so libnspr4.so libatk-1.0.so libgbm.so libasound.so; do
        case "$known" in
            *"$lib"*) ;;
            *) return 1 ;;
        esac
    done
    return 0
}

_ffmpeg_ok() {
    command -v ffmpeg >/dev/null 2>&1
}

cmd_check() {
    local ok=0
    _node_ok        || ok=1
    _chromium_ok    || ok=1
    _system_deps_ok || ok=1
    _ffmpeg_ok      || ok=1
    return "$ok"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
_install_chromium_binary() {
    if _chromium_ok; then
        echo "  ok Playwright Chromium already installed - skip"
    else
        echo "  Installing Playwright Chromium (npx -y playwright@${PW_PIN} install chromium)..."
        npx -y "playwright@${PW_PIN}" install chromium
        echo "  ok Playwright Chromium installed"
    fi
}

# Chromium shared system libraries. apt-based Linux only - macOS/Windows and
# non-apt Linux need no extra OS packages, so this is a no-op there.
_ensure_system_deps() {
    _is_apt_linux || return 0

    if _system_deps_ok; then
        echo "  ok Chromium system libraries present - skip"
        return 0
    fi

    if _can_sudo_nopasswd; then
        echo "  Installing Chromium system libraries (passwordless sudo detected)..."
        if sudo -n env "PATH=$PATH" npx -y "playwright@${PW_PIN}" install-deps chromium; then
            echo "  ok Chromium system libraries installed"
            return 0
        fi
        # We had sudo and actively tried: a failure here is a REAL error, not
        # advice. Surface it (caller fails the step) - never swallow it.
        echo "  x Failed to install Chromium system libraries." >&2
        echo "    Retry manually: sudo npx -y playwright@${PW_PIN} install-deps chromium" >&2
        return 1
    fi

    # No passwordless sudo: installing system packages would require a silent
    # sudo (a hard rule we never break). This is a user action, not a script
    # failure - advise the exact command and let `check` report not-ready so the
    # missing libs are surfaced, never hidden.
    echo "  ! Chromium system libraries are missing (needed by playwright + pagecast)." >&2
    echo "    No passwordless sudo available - run this once yourself" >&2
    echo "    (NO sudo is ever run for you):" >&2
    echo "      sudo npx -y playwright@${PW_PIN} install-deps chromium" >&2
    return 0
}

_ffmpeg_guidance() {
    echo "  ffmpeg is missing - needed by the pagecast server for GIF/video"
    echo "  recording. Install it manually (NO sudo will be run for you):"
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

    _install_chromium_binary
    _ensure_system_deps || return 1

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
