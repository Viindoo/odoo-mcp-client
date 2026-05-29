#!/usr/bin/env bash
# 50-instance-spinup.sh - Start a declared Odoo instance and wait for HTTP 200.
#
# Reads an instance profile written by 40-instance-profile.sh from
# .odoo-ai/instances.toml, generates a temporary odoo.conf with the correct
# addons_path ordering, launches Odoo (source via odoo-bin OR docker compose),
# then polls /web/login until it answers HTTP 200 (or times out).
#
# Unlike the other steps this one is PARAMETERISED by version:
#   50-instance-spinup.sh apply --version 17.0
#   50-instance-spinup.sh check --version 17.0
# If --version is omitted, the FIRST [instance.*] table in the file is used.
#
# Subcommands:
#   describe   One-line description.
#   check      Exit 0 if the instance's http_port already answers HTTP 200
#              (already running); exit 1 otherwise.
#   apply      Generate conf, spin up, poll until 200 (timeout ~120s), print URL.
#
# HARD RULES:
#   - Reads db_password ONLY from env (ODOO_PG_PASSWORD) - never from the TOML.
#   - The generated odoo.conf goes in a temp dir; no project files are mutated.
#   - No sudo. docker mode uses `docker compose` (must already be installed).
#
# CONFIG:
#   ODOO_AI_DIR        ${ODOO_AI_DIR:-$PWD/.odoo-ai}
#   ODOO_BIN           path to odoo-bin (source mode). Auto-detected from
#                      the 'core' addons_path entry if unset.
#   ODOO_PG_PASSWORD   postgres password (env only; optional for trust auth).
#   SPINUP_TIMEOUT     poll timeout seconds (default 120).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ODOO_AI_DIR="${ODOO_AI_DIR:-$PWD/.odoo-ai}"
INSTANCES_TOML="$ODOO_AI_DIR/instances.toml"
SPINUP_TIMEOUT="${SPINUP_TIMEOUT:-120}"

# ---------------------------------------------------------------------------
# arg parse: subcommand first, then optional --version X.Y
# ---------------------------------------------------------------------------
SUBCMD="${1:-}"
shift || true
VERSION=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --version)
            # Guard: a bare trailing `--version` leaves only 1 arg, so `shift 2`
            # would return 1 and (under set -e) abort the script silently.
            if [[ $# -lt 2 ]]; then
                echo "$(basename "$0") --version requires a value (e.g. --version 17.0)" >&2
                exit 2
            fi
            VERSION="$2"; shift 2 ;;
        *) echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# describe
# ---------------------------------------------------------------------------
cmd_describe() {
    echo "Spin up a declared Odoo instance (source or docker) and wait for HTTP 200 on /web/login"
}

# ---------------------------------------------------------------------------
# TOML reader - emit shell-eval-able KEY=VALUE lines for one instance table.
# Uses tomllib (py3.11+); falls back to a minimal `[instance.<key>]` text scan
# on older Python so spin-up still works without a 3.11 interpreter.
# ---------------------------------------------------------------------------
_read_instance() {
    # $1 = version (may be empty -> first table).
    # Prints shell-safe KEY=VALUE lines (values quoted via shlex.quote) so the
    # caller can `eval` them safely even when a path contains spaces or shell
    # metacharacters (e.g. macOS "/Users/me/My Repos/odoo").
    [[ -f "$INSTANCES_TOML" ]] || return 1
    python3 - "$INSTANCES_TOML" "${1:-}" <<'PY'
import sys, shlex, re
path, want = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "")

def _load_tomllib(p):
    import tomllib  # py3.11+; ImportError -> caller falls back to text scan
    with open(p, "rb") as f:
        return tomllib.load(f)

def _load_textscan(p):
    """Minimal fallback parser for `[instance.<key>]` tables on Python < 3.11.

    Handles the subset this file writes: string/int scalars and inline arrays
    of strings. Not a general TOML parser — just enough for instances.toml.
    """
    def parse_value(raw):
        raw = raw.strip()
        if raw.startswith("[") and raw.endswith("]"):
            items = []
            for part in raw[1:-1].split(","):
                part = part.strip().strip('"').strip("'")
                if part:
                    items.append(part)
            return items
        if (raw.startswith('"') and raw.endswith('"')) or \
           (raw.startswith("'") and raw.endswith("'")):
            return raw[1:-1]
        if re.fullmatch(r"-?\d+", raw):
            return int(raw)
        return raw
    inst, cur = {}, None
    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"^\[instance\.([^\]]+)\]$", line)
            if m:
                cur = m.group(1).strip().strip('"').strip("'")
                inst[cur] = {}
                continue
            if cur is None or line.startswith("["):
                # A non-instance table ends the current instance scope.
                if line.startswith("["):
                    cur = None
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                inst[cur][k.strip()] = parse_value(v)
    return {"instance": inst}

try:
    data = _load_tomllib(path)
except ImportError:
    try:
        data = _load_textscan(path)
    except Exception:
        sys.exit(1)
except Exception:
    sys.exit(1)
inst = (data.get("instance") or {})
if not inst:
    sys.exit(1)
if want:
    tbl = inst.get(want)
    key = want
else:
    key = sorted(inst)[0]
    tbl = inst[key]
if not isinstance(tbl, dict):
    sys.exit(1)
def sh(v):
    if isinstance(v, list):
        return ":".join(str(x) for x in v)
    return str(v)
def emit(name, value):
    # shlex.quote makes the RHS a single, injection-safe shell word.
    print(f"{name}={shlex.quote(sh(value))}")
emit("INST_VERSION", tbl.get('version', key))
emit("INST_ADDONS_PATH", tbl.get('addons_path', []))
emit("INST_RUN_MODE", tbl.get('run_mode', 'source'))
emit("INST_HTTP_PORT", tbl.get('http_port', 8069))
emit("INST_DB_NAME", tbl.get('db_name', 'odoo'))
emit("INST_DB_HOST", tbl.get('db_host', 'localhost'))
emit("INST_DB_USER", tbl.get('db_user', 'odoo'))
PY
}

# ---------------------------------------------------------------------------
# HTTP probe - returns the status code on /web/login (000 on connection fail)
# ---------------------------------------------------------------------------
_http_status() {
    # $1 = port
    curl -s -o /dev/null -w "%{http_code}" "http://localhost:$1/web/login" 2>/dev/null || echo "000"
}

# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------
cmd_check() {
    local kv port
    kv="$(_read_instance "$VERSION")" || return 1
    eval "$kv"
    port="${INST_HTTP_PORT:-8069}"
    [[ "$(_http_status "$port")" == "200" ]]
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
_find_odoo_bin() {
    # Locate odoo-bin: explicit env wins, else search the addons_path entries
    # one level up for an odoo-bin (the 'core' repo root).
    if [[ -n "${ODOO_BIN:-}" && -x "${ODOO_BIN}" ]]; then
        echo "$ODOO_BIN"; return 0
    fi
    local p
    IFS=':' read -ra _paths <<<"${INST_ADDONS_PATH:-}"
    for p in "${_paths[@]}"; do
        [[ -n "$p" ]] || continue
        if [[ -x "$p/odoo-bin" ]]; then echo "$p/odoo-bin"; return 0; fi
        if [[ -x "$(dirname "$p")/odoo-bin" ]]; then echo "$(dirname "$p")/odoo-bin"; return 0; fi
    done
    return 1
}

_poll_until_up() {
    # $1 = port. Poll /web/login until 200 or timeout. Returns 0 on success.
    local port="$1" elapsed=0 status
    echo "  Polling http://localhost:$port/web/login (timeout ${SPINUP_TIMEOUT}s)..."
    while (( elapsed < SPINUP_TIMEOUT )); do
        status="$(_http_status "$port")"
        if [[ "$status" == "200" ]]; then
            echo "  ok HTTP 200 after ${elapsed}s"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    echo "  x timed out after ${SPINUP_TIMEOUT}s (last status: ${status:-000})" >&2
    return 1
}

cmd_apply() {
    local kv
    kv="$(_read_instance "$VERSION")" || {
        echo "x No instance found in $INSTANCES_TOML. Run step 40 first." >&2
        return 1
    }
    eval "$kv"
    local port="${INST_HTTP_PORT:-8069}"

    if [[ "$(_http_status "$port")" == "200" ]]; then
        echo "ok Instance ${INST_VERSION} already up at http://localhost:$port/web/login"
        return 0
    fi

    # Tracked so a poll timeout can kill the orphaned process / remove temp conf
    # instead of leaking a port-holding Odoo and a /tmp conf file.
    local run_mode="${INST_RUN_MODE:-source}"
    local odoo_pid="" conf=""

    case "$run_mode" in
        docker)
            if ! command -v docker >/dev/null 2>&1; then
                echo "x run_mode=docker but 'docker' not found in PATH." >&2
                return 1
            fi
            echo "  Starting via 'docker compose up -d' in $PWD..."
            docker compose up -d
            ;;
        source)
            local bin
            bin="$(_find_odoo_bin)" || {
                echo "x Could not locate odoo-bin. Set ODOO_BIN=/path/to/odoo-bin and retry." >&2
                return 1
            }
            conf="$(mktemp -t odoo-spinup-${INST_VERSION}.XXXXXX.conf)"
            {
                echo "[options]"
                echo "addons_path = $(printf '%s' "${INST_ADDONS_PATH:-}" | tr ':' ',')"
                echo "http_port = $port"
                echo "db_name = ${INST_DB_NAME:-odoo}"
                echo "db_host = ${INST_DB_HOST:-localhost}"
                echo "db_user = ${INST_DB_USER:-odoo}"
                # Password ONLY from env - never echoed from a stored file.
                if [[ -n "${ODOO_PG_PASSWORD:-}" ]]; then
                    echo "db_password = ${ODOO_PG_PASSWORD}"
                fi
            } >"$conf"
            echo "  Generated temp conf: $conf"
            echo "  Launching: python '$bin' -c '$conf' -d '${INST_DB_NAME:-odoo}' --dev=all"
            # Run in background so we can poll. Logs to a temp file.
            # Capture the PID directly (no subshell `( )`, which would hide it)
            # so a poll timeout can terminate the orphaned process.
            local logf
            logf="$(mktemp -t odoo-spinup-${INST_VERSION}.XXXXXX.log)"
            python3 "$bin" -c "$conf" -d "${INST_DB_NAME:-odoo}" --dev=all >"$logf" 2>&1 &
            odoo_pid=$!
            echo "  Odoo starting (pid: $odoo_pid, log: $logf)"
            ;;
        *)
            echo "x Unknown run_mode: ${INST_RUN_MODE}. Use 'source' or 'docker'." >&2
            return 1
            ;;
    esac

    if _poll_until_up "$port"; then
        echo "ok Odoo ${INST_VERSION} is up: http://localhost:$port/web/login"
        return 0
    fi

    # Poll timed out — tear down what we started so we leave no orphan.
    echo "x Odoo did not become ready. Check the launch log above." >&2
    if [[ "$run_mode" == "source" ]]; then
        if [[ -n "$odoo_pid" ]]; then
            echo "  Stopping background Odoo (pid $odoo_pid)" >&2
            kill "$odoo_pid" 2>/dev/null || true
        fi
        [[ -n "$conf" && -f "$conf" ]] && rm -f "$conf"
    elif [[ "$run_mode" == "docker" ]]; then
        echo "  Tip: run 'docker compose down' to stop the containers started above." >&2
    fi
    return 1
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
case "$SUBCMD" in
    describe) cmd_describe ;;
    check)    cmd_check ;;
    apply)    cmd_apply ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply} [--version X.Y]" >&2; exit 2 ;;
esac
