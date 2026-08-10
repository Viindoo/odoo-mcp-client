#!/usr/bin/env bash
# pg_mode.sh - detect the DECLARED Postgres client surface for one instance.
#
# SSOT for the db_run_mode vocabulary. Sourced by 40-instance-profile.sh (declare
# time), 45-venv.sh (verify + retrofit), 50-instance-spinup.sh (preflight
# dispatch), 05-prereq-check.sh (report). Runtime consumers NEVER call this -
# they read the declared db_run_mode from instances.toml via instances_io.py.
#
#   native    libpq client binaries on PATH reach this cluster
#   docker    the cluster runs in the container named by db_container; client
#             binaries are reached with `docker exec <db_container>`
#   tcp-only  no client surface on this host; every operation goes through the
#             instance's own `python` (psycopg2 via Odoo) over TCP
#
# db_run_mode describes POSTGRES. run_mode describes ODOO. They are independent:
# a source-mode Odoo instance routinely talks to a containerized cluster.
#
# Detection NEVER guesses. An ambiguous docker match, docker as the only
# candidate with no declared db_port, a `docker ps` that could not be asked, or a
# publishing container that exists but is STOPPED all exit 3 and write NOTHING to
# stdout - the caller must then record no mode at all rather than a guessed one.
#
# Detection says NOTHING about REACHABILITY. "No client installed" and "cluster
# down" are separate facts, verified separately (a live connection through the
# instance's own python is the reachability probe) - conflating them is the
# false-negative shape that silently destroyed ephemeral isolation.

PG_MODE_NATIVE_BINS=(psql dropdb)

# Absolute path of THIS file, captured at source time. pg_bounded_run re-enters
# bash and re-sources it to bound a shell FUNCTION (see there); resolving the
# path here is the only place it is knowable.
PG_MODE_SH_SELF="${BASH_SOURCE[0]}"

_pg_mode_have() { command -v "$1" >/dev/null 2>&1; }

# _pg_mode_container_names <db_port> [--all]
#   stdout: one container name per line for containers publishing <db_port>.
#   exit:   0 asked and answered (zero rows is a valid answer) | 1 could not ask.
#   `docker ps`'s exit status is the ONLY signal separating "no container
#   publishes that port" from "I could not ask" - swallowing it (2>/dev/null ||
#   true) turns a daemon outage into a durable, wrong, never-re-derived catalog
#   fact. `--filter publish=` matches the HOST-side published port only, which is
#   exactly the mapping db_port names.
_pg_mode_container_names() {
    local db_port="$1" all="${2:-}" out="" rc=0
    if [[ "$all" == "--all" ]]; then
        out="$(docker ps -a --filter "publish=${db_port}" --format '{{.Names}}' 2>/dev/null)" || rc=$?
    else
        out="$(docker ps --filter "publish=${db_port}" --format '{{.Names}}' 2>/dev/null)" || rc=$?
    fi
    [[ "$rc" -eq 0 ]] || return 1
    printf '%s\n' "$out"
    return 0
}

# pg_detect_mode [db_port]
#   stdout: `db_run_mode=<v>` and, for docker, `db_container=<name>`
#   exit:   0 determined | 3 undeterminable (message on stderr, no stdout)
pg_detect_mode() {
    local db_port="${1:-}" b native=1
    for b in "${PG_MODE_NATIVE_BINS[@]}"; do
        _pg_mode_have "$b" || { native=0; break; }
    done
    if [[ "$native" -eq 1 ]]; then
        # Native WINS over a co-present container: a native client serves every
        # operation with no container-name dependency (a container is renamed by
        # any compose project-dir change). Recording both would put one fact in
        # two places.
        printf 'db_run_mode=native\n'
        return 0
    fi
    if ! _pg_mode_have docker; then
        printf 'db_run_mode=tcp-only\n'
        return 0
    fi
    if [[ -z "$db_port" ]]; then
        echo "pg_mode: docker is the only candidate client surface, but this instance declares no" >&2
        echo "  db_port, so the container serving it cannot be identified. Declare db_port (the" >&2
        echo "  published host port of your Postgres container) on this [[instance]], or declare" >&2
        echo "  db_container by hand. Nothing was recorded." >&2
        return 3
    fi
    local -a hits=()
    local line names=""
    if ! names="$(_pg_mode_container_names "$db_port")"; then
        echo "pg_mode: 'docker ps' failed, so no answer about port ${db_port} is available -" >&2
        echo "  and 'no container publishes it' is NOT the same fact as 'I could not ask'." >&2
        echo "  Start the docker daemon (or fix its permissions) and re-run, or declare" >&2
        echo "  db_run_mode + db_container by hand. Nothing was recorded." >&2
        return 3
    fi
    while IFS= read -r line; do
        [[ -n "$line" ]] && hits+=("$line")
    done <<<"$names"
    case "${#hits[@]}" in
        0)
            # ZERO RUNNING matches is still ambiguous: `docker ps` lists running
            # containers only, so a Postgres container that simply has not been
            # started yet looks identical to a host with no container at all -
            # and the two imply OPPOSITE durable facts. Ask again including
            # stopped containers; a stopped candidate is refused by name rather
            # than silently recorded as tcp-only.
            local stopped=""
            local -a scand=()
            if stopped="$(_pg_mode_container_names "$db_port" --all)"; then
                while IFS= read -r line; do
                    [[ -n "$line" ]] && scand+=("$line")
                done <<<"$stopped"
            fi
            if [[ "${#scand[@]}" -gt 0 ]]; then
                echo "pg_mode: container(s) ${scand[*]} publish port ${db_port} but none is RUNNING," >&2
                echo "  so this host's client surface cannot be determined yet. Start the cluster," >&2
                echo "  then re-run '45-venv.sh record-env'. Nothing was recorded." >&2
                return 3
            fi
            printf 'db_run_mode=tcp-only\n'; return 0 ;;
        1) printf 'db_run_mode=docker\ndb_container=%s\n' "${hits[0]}"; return 0 ;;
        *) echo "pg_mode: ${#hits[@]} containers publish port ${db_port} (${hits[*]}) - refusing to guess." >&2
           echo "  Declare db_container explicitly on this [[instance]]. Nothing was recorded." >&2
           return 3 ;;
    esac
}

# Default wall-clock bound (seconds) for a reachability/capability PROBE.
# A probe is a preflight, so it must never be able to outlive the thing it
# gates: an interpreter that hangs (an unreachable cluster with no connect
# timeout, a broken venv wrapper) would otherwise stall a spin-up indefinitely,
# which is strictly worse than the wrong answer it was added to prevent.
PG_MODE_PROBE_TIMEOUT="${ODOO_AI_PG_PROBE_TIMEOUT:-10}"

# _pg_mode_norm_secs <value>
#   stdout: <value> as a decimal integer with leading zeros stripped.
#   exit:   0 usable | 2 not a number (message on stderr).
#   Normalising ONCE, at entry, is what keeps every numeric comparison below
#   safe: bash arithmetic contexts (`[[ -ge ]]`, `(( ))`) read a leading zero as
#   an OCTAL prefix, so a perfectly ordinary "08" raises "value too great for
#   base" - the comparison is then never true and the wait loop spins forever
#   with the child alive, which is precisely the unbounded hang this function
#   exists to prevent.
_pg_mode_norm_secs() {
    local raw="${1:-}"
    if [[ ! "$raw" =~ ^[0-9]+$ ]]; then
        echo "pg_mode: invalid probe bound '${raw}' - expected a whole number of seconds." >&2
        return 2
    fi
    raw="${raw#"${raw%%[!0]*}"}"
    printf '%s\n' "${raw:-0}"
}

# pg_bounded_run <seconds> <cmd> [args...]
#   Run <cmd> with a hard wall-clock bound. <cmd> may be a BINARY or a shell
#   FUNCTION defined by this file (pg_run_client is both real callers' callee).
#   Exit: the command's own status, or
#     124 the bound elapsed - "could not answer in time"
#     125 the bound itself could not be applied (a non-numeric <seconds>)
#   Callers MUST treat 124 AND 125 as UNDETERMINED, never as a factual negative:
#   neither says anything about the thing being probed.
#   `timeout` is used when available (it is not POSIX) and a background +
#   bounded-wait loop otherwise.
pg_bounded_run() {
    local secs
    secs="$(_pg_mode_norm_secs "$1")" || return 125
    shift
    # A shell FUNCTION cannot be exec'd: `timeout` is a coreutils BINARY, so
    # handing it a function name yields "timeout: failed to execute process" and
    # exit 127 - which every caller reads as a factual negative about the
    # cluster. Re-enter bash (via $BASH, so no PATH lookup is needed) and
    # re-source this file, then bound THAT: one ladder, identical semantics for
    # binaries and functions alike.
    if [[ "$(type -t "$1" 2>/dev/null)" == "function" ]]; then
        set -- "${BASH:-bash}" -c 'source "$1"; shift; "$@"' pg_bounded_run \
                "$PG_MODE_SH_SELF" "$@"
    fi
    if _pg_mode_have timeout; then
        timeout "$secs" "$@"
        return $?
    fi
    "$@" &
    local pid=$! rc=0
    # WALL CLOCK, not an iteration count. $SECONDS is a bash builtin, so the
    # bound holds even when the pacing `sleep` below is missing or fails - an
    # iteration-counting loop would silently collapse the bound to ~0s on
    # exactly the hosts that have no `timeout` binary to check it with.
    local started=$SECONDS
    while kill -0 "$pid" 2>/dev/null; do
        if (( SECONDS - started >= secs )); then
            kill -TERM "$pid" 2>/dev/null || true
            sleep 1 2>/dev/null || true
            kill -KILL "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true
            return 124
        fi
        # Pacing only - best effort by design (see the wall-clock note above).
        sleep 1 2>/dev/null || true
    done
    wait "$pid" || rc=$?
    return "$rc"
}

# pg_run_client <db_run_mode> <db_container> <db_host> <db_user> <db_port> <bin> [args...]
#   Run a libpq client against this cluster in the DECLARED mode. Exit 3 when the
#   mode offers no client surface - the caller MUST fail loudly, never treat a
#   missing client as a completed operation.
#   PARITY: mirrors allocator.py `_pg_client_argv`; keep in lockstep (guard:
#   tests/test_pg_mode.py::test_shell_and_python_client_dispatch_agree).
pg_run_client() {
    local mode="$1" container="$2" host="$3" user="$4" port="$5" bin="$6"; shift 6
    case "$mode" in
        native)
            local -a conn=(-h "$host" -U "$user")
            [[ -n "$port" ]] && conn+=(-p "$port")
            "$bin" "${conn[@]}" "$@"
            ;;
        docker)
            [[ -n "$container" ]] || { echo "pg_mode: db_run_mode=docker but db_container is empty." >&2; return 3; }
            # The command runs INSIDE the container, where the declared host and
            # the PUBLISHED port do not exist: the mapping is a host-side fact and
            # <host> resolves to the container's own loopback. Connect over the
            # container's local socket (-U only). Passing the published port here
            # would target a port nothing listens on inside the container - the
            # silent wrong-cluster shape the drop surface already guards against.
            local -a pre=(docker exec)
            if [[ -n "${ODOO_PG_PASSWORD:-}" ]]; then
                # `-e PGPASSWORD` forwards the value BY NAME so it never appears
                # in the process table - which means PGPASSWORD must exist in
                # THIS process's environment. The plugin's own knob is
                # ODOO_PG_PASSWORD, so it is exported under libpq's name for this
                # one call; mirrors allocator.py's `_pg_env`. Without this the
                # flag forwards an unset variable and the client authenticates
                # with no password at all.
                pre+=(-e PGPASSWORD)
                PGPASSWORD="${ODOO_PG_PASSWORD}" \
                    "${pre[@]}" -i "$container" "$bin" -U "$user" "$@"
                return $?
            fi
            "${pre[@]}" -i "$container" "$bin" -U "$user" "$@"
            ;;
        *)
            echo "pg_mode: no libpq client surface for db_run_mode=${mode:-<absent>}." >&2
            return 3
            ;;
    esac
}
