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
# The same contract binds pg_origin_address, pg_publish_is_loopback_only and
# pg_hba_file_path below: each ASKS the container or the server and exits 3 with
# an empty stdout when it cannot be answered. A guessed bridge gateway would
# authorise an address the plugin's connections never come from, which is
# strictly worse than authorising none.
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
#   BOUNDED: a wedged docker daemon answers nothing, and this question is asked on
#   the declare path AND on the mutating path - an unbounded hang there is the same
#   never-returning step the bound exists to prevent everywhere else. A bound that
#   elapsed is "could not ask" (exit 1), which is exactly what this function
#   already promises for a daemon that refused.
_pg_mode_container_names() {
    local db_port="$1" all="${2:-}" out="" rc=0
    if [[ "$all" == "--all" ]]; then
        out="$(pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
            docker ps -a --filter "publish=${db_port}" --format '{{.Names}}' 2>/dev/null)" || rc=$?
    else
        out="$(pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
            docker ps --filter "publish=${db_port}" --format '{{.Names}}' 2>/dev/null)" || rc=$?
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

# Seconds between SIGTERM and SIGKILL once the bound has elapsed. Escalation is
# not optional: a TERM-only bound is defeated entirely by a child that traps or
# ignores the signal, and the wait then never ends - the unbounded hang the bound
# exists to prevent. Both arms of pg_bounded_run escalate through this ONE value.
PG_MODE_KILL_GRACE="${ODOO_AI_PG_KILL_GRACE:-1}"

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

# _pg_mode_kill_tree <pid>
#   TERM then KILL the process GROUP led by <pid>, falling back to <pid> itself
#   when no group is led by it.
#
#   Signalling the direct child alone does NOT bound the wall clock, because every
#   real callee here reaches libpq through at least one intermediate shell (the
#   FUNCTION arm re-enters bash; `pg_run_client` then forks psql), so the client is
#   a GRANDCHILD. It inherits the caller's stdout pipe, and a caller written as
#   `out="$(pg_bounded_run ...)"` cannot return while any process holds that pipe
#   open - so the substitution waits for libpq's full TCP timeout (psycopg2/libpq
#   are given no connect_timeout) and then delivers the LATE bytes alongside status
#   124. MEASURED before this was fixed: a 2s bound returned after 8s carrying the
#   killed child's output, with the grandchild still alive afterwards.
_pg_mode_kill_tree() {
    local pid="$1"
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    sleep "$PG_MODE_KILL_GRACE" 2>/dev/null || true
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

# _pg_mode_bg <cmd> [args...]
#   Start <cmd> as the LEADER of its own process group and leave its pid in `$!`
#   for the caller (a bash function does not fork, so `$!` is the caller's own).
#
#   `set -m` (job control) is what creates the group: without it the child shares
#   THIS script's group and `kill -- -<pid>` would signal the script itself. It is
#   enabled for the fork alone and restored immediately.
#
#   A TTY stdin is replaced by /dev/null, and that is not cosmetic: a background
#   process group that READS the controlling terminal is stopped by SIGTTIN
#   (verified: process state T), and `docker exec -i` forwards stdin
#   unconditionally - so on an interactive run every docker-mode probe would stop
#   forever and the bound would report 124 for a cluster that was answering fine.
#   A tty carries nothing a probe could want. A FILE or PIPE on stdin is the
#   deliberate case (48-db-local-auth.sh pipes the new file contents in) and is
#   passed through untouched.
_pg_mode_bg() {
    local had_monitor=0
    case "$-" in *m*) had_monitor=1 ;; esac
    set -m
    if [[ -t 0 ]]; then
        "$@" </dev/null &
    else
        "$@" &
    fi
    [[ "$had_monitor" -eq 1 ]] || set +m
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
#   bounded-wait loop otherwise. BOTH arms signal a process GROUP, never the
#   direct child alone - see _pg_mode_kill_tree.

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
        # `timeout` is still preferred (it needs no polling loop), but its group
        # behaviour is NOT guaranteed: POSIX does not specify it, GNU coreutils
        # signals the group while other implementations signal only their direct
        # child. So it runs as a group leader here and the group is swept whenever
        # the bound elapsed - one contract on every host, whichever `timeout` is
        # installed.
        _pg_mode_bg timeout -k "$PG_MODE_KILL_GRACE" "$secs" "$@"
        local tpid=$! trc=0
        wait "$tpid" || trc=$?
        # A child that TRAPS or IGNORES SIGTERM survives the bound's first signal
        # and is killed only after the grace, at which point `timeout` reports
        # 128+SIGKILL rather than its own 124. Both mean ONE thing - the bound
        # elapsed, nothing was answered - and every caller special-cases 124
        # alone, so 137 must never reach them: read as a command status it becomes
        # a factual negative about the cluster. Normalise here, where the reason
        # is known, so the two arms of this function cannot disagree.
        if [[ "$trc" -eq 124 || "$trc" -eq 137 ]]; then
            _pg_mode_kill_tree "$tpid"
            return 124
        fi
        return "$trc"
    fi
    _pg_mode_bg "$@"
    local pid=$! rc=0
    # WALL CLOCK, not an iteration count. $SECONDS is a bash builtin, so the
    # bound holds even when the pacing `sleep` below is missing or fails - an
    # iteration-counting loop would silently collapse the bound to ~0s on
    # exactly the hosts that have no `timeout` binary to check it with.
    local started=$SECONDS
    while kill -0 "$pid" 2>/dev/null; do
        if (( SECONDS - started >= secs )); then
            _pg_mode_kill_tree "$pid"
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

# --------------------------------------------------------------------------- #
# WHERE DOES THE PLUGIN'S CONNECTION ARRIVE FROM, and may that address be
# trusted? Both questions are asked of the container, never assumed.
#
# A host-side connection to a PUBLISHED container port does NOT arrive as
# loopback: the publish path re-originates it from the bridge gateway. So the
# rule a human would naturally write - trusting 127.0.0.1 - is already present in
# the stock image and already dead. The gateway also DIFFERS between the default
# bridge and a user-defined/compose network on one machine, so it is a per-
# container fact with no correct constant.
# --------------------------------------------------------------------------- #

# _pg_mode_is_loopback_addr <addr>
#   0 when <addr> is an IPv4 loopback (127.0.0.0/8) or the IPv6 loopback.
#   An EMPTY HostIp means "every interface" in docker's own vocabulary, so it is
#   NOT loopback - reading it as one is how a routable publish would slip past the
#   safety gate.
_pg_mode_is_loopback_addr() {
    case "${1:-}" in
        127.*) return 0 ;;
        ::1|0:0:0:0:0:0:0:1) return 0 ;;
        *) return 1 ;;
    esac
}

# _pg_mode_addr_with_prefix <addr>
#   stdout: `<addr>/32` for an IPv4 literal, `<addr>/128` for an IPv6 one.
#   exit:   0 emitted | 1 not an address literal (nothing on stdout).
#   The prefix length is attached HERE, once: a bare address in a pg_hba rule
#   means a HOST NAME to Postgres, and a wider prefix would trust every other
#   container on the bridge.
_pg_mode_addr_with_prefix() {
    local a="${1:-}"
    [[ -n "$a" ]] || return 1
    if [[ "$a" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]]; then
        printf '%s/32\n' "$a"
        return 0
    fi
    if [[ "$a" == *:* && "$a" =~ ^[0-9A-Fa-f:]+$ ]]; then
        printf '%s/128\n' "$a"
        return 0
    fi
    return 1
}

# pg_origin_address <container>
#   stdout: one `<addr>/<prefixlen>` per line - every DISTINCT gateway of every
#           network the container is attached to.
#   exit:   0 at least one address emitted | 3 undeterminable (nothing on stdout).
#   Two rungs, because a container attached to a user-defined network may report
#   no Gateway of its own while the network object still declares one:
#     1. the container's NetworkSettings.Networks[*].Gateway / IPv6Gateway
#     2. `docker network inspect <net>` IPAM.Config[*].Gateway
pg_origin_address() {
    local container="${1:-}"
    [[ -n "$container" ]] || {
        echo "pg_mode: pg_origin_address needs a container name; none given." >&2
        return 3
    }
    _pg_mode_have docker || {
        echo "pg_mode: docker is not on PATH, so the address this host's connections" >&2
        echo "  arrive from cannot be asked. Nothing was emitted." >&2
        return 3
    }
    local raw="" nets="" a out="" line
    raw="$(docker inspect "$container" \
        --format '{{range .NetworkSettings.Networks}}{{.Gateway}}
{{.IPv6Gateway}}
{{end}}' 2>/dev/null)" || raw=""
    while IFS= read -r a; do
        [[ -n "$a" ]] || continue
        line="$(_pg_mode_addr_with_prefix "$a")" || continue
        case "
$out" in *"
$line
"*) continue ;; esac
        out="$out$line
"
    done <<<"$raw"
    if [[ -z "$out" ]]; then
        # Rung 2: ask the NETWORK objects the container is attached to.
        nets="$(docker inspect "$container" \
            --format '{{range $n, $v := .NetworkSettings.Networks}}{{$n}}
{{end}}' 2>/dev/null)" || nets=""
        local net graw
        while IFS= read -r net; do
            [[ -n "$net" ]] || continue
            graw="$(docker network inspect "$net" \
                --format '{{range .IPAM.Config}}{{.Gateway}}
{{end}}' 2>/dev/null)" || continue
            while IFS= read -r a; do
                [[ -n "$a" ]] || continue
                line="$(_pg_mode_addr_with_prefix "$a")" || continue
                case "
$out" in *"
$line
"*) continue ;; esac
                out="$out$line
"
            done <<<"$graw"
        done <<<"$nets"
    fi
    if [[ -z "$out" ]]; then
        echo "pg_mode: neither container ${container} nor its networks declare a gateway," >&2
        echo "  so the address this host's connections arrive from is unknown. Refusing to" >&2
        echo "  guess one: a trust rule for an address nothing arrives from authorises a" >&2
        echo "  stranger and fixes nothing. Nothing was emitted." >&2
        return 3
    fi
    printf '%s' "$out"
    return 0
}

# pg_publish_is_loopback_only <container>
#   exit: 0 every published binding is on a loopback HostIp
#         1 at least one binding is NOT loopback (the address is named on stderr)
#         3 the question could not be asked (no docker, inspect failed, or the
#           container publishes nothing at all)
#   Trusting the gateway trusts THE HOST, so a port published on a routable
#   address would extend that trust to anyone who can reach the host.
pg_publish_is_loopback_only() {
    local container="${1:-}"
    [[ -n "$container" ]] || return 3
    _pg_mode_have docker || return 3
    local raw=""
    raw="$(docker inspect "$container" \
        --format '{{range $p, $bs := .NetworkSettings.Ports}}{{range $bs}}{{$p}} {{.HostIp}}
{{end}}{{end}}' 2>/dev/null)" || return 3
    local seen=0 port ip bad=0 line
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        port="${line%% *}"; ip="${line#* }"
        seen=$((seen + 1))
        if ! _pg_mode_is_loopback_addr "$ip"; then
            bad=$((bad + 1))
            echo "pg_mode: ${container} publishes ${port} on HostIp '${ip}', which is not a" >&2
            echo "  loopback address." >&2
        fi
    done <<<"$raw"
    [[ "$seen" -gt 0 ]] || return 3
    [[ "$bad" -eq 0 ]] || return 1
    return 0
}

# --------------------------------------------------------------------------- #
# WHY did that question fail? - a channel that survives a command substitution.
#
# Every question here is asked as `out="$(...)"`, which runs in a SUBSHELL: a
# variable the callee sets is LOST the moment it returns, so the server's own error
# line cannot travel back in one. It travels through a FILE the CALLER opens
# instead. Without this the distinction below is unreachable, which is how a
# "permission denied" came to be reported as "your cluster does not have that".
#
# Usage:  pg_err_open once (per script run); after any call, pg_err_denied /
#         pg_err_text; pg_err_close when done.
# --------------------------------------------------------------------------- #
PG_ERR_FILE=""

pg_err_open() {
    PG_ERR_FILE="$(mktemp 2>/dev/null)" || PG_ERR_FILE=""
    return 0
}

pg_err_close() {
    [[ -n "$PG_ERR_FILE" ]] && rm -f "$PG_ERR_FILE"
    PG_ERR_FILE=""
    return 0
}

# pg_err_sink: the stderr target for ONE call - the channel when open (truncated
# first, so a stale message can never be read as this call's), else /dev/null.
pg_err_sink() {
    if [[ -n "$PG_ERR_FILE" ]]; then
        : >"$PG_ERR_FILE" 2>/dev/null || { printf '%s\n' /dev/null; return 0; }
        printf '%s\n' "$PG_ERR_FILE"
        return 0
    fi
    printf '%s\n' /dev/null
}

pg_err_text() {
    [[ -n "$PG_ERR_FILE" && -s "$PG_ERR_FILE" ]] || return 0
    head -n 1 "$PG_ERR_FILE" 2>/dev/null
    return 0
}

# pg_err_denied: 0 when the server said the question was not PERMITTED - as
# opposed to unavailable, unanswered, or never asked. The three wordings
# PostgreSQL has used for a superuser-only GUC / function / view across versions.
pg_err_denied() {
    case "$(pg_err_text)" in
        *"permission denied"*|*"must be superuser"*|*"permission to examine"*)
            return 0 ;;
    esac
    return 1
}

# pg_hba_file_path <db_run_mode> <db_container> <db_host> <db_user> <db_port>
#   stdout: the absolute path of the cluster's ACTIVE pg_hba.conf, as the running
#           server reports it (`SHOW hba_file`).
#   exit:   0 answered | 3 could not be asked (nothing on stdout).
#   The server's own error line is left on the pg_err channel, so a caller can tell
#   "not PERMITTED" from "did not answer". `hba_file` is GUC_SUPERUSER_ONLY, so a
#   role created with CREATEDB but not SUPERUSER - an ordinary, correct way to
#   provision an Odoo role - gets a permission error from a cluster that is running
#   perfectly. Without that distinction the only remedy a caller could name was
#   "start the cluster", which is advice to restart something that is already up.
#   BOUNDED like every other question asked here: this one is on the MUTATING
#   path, so an unbounded hang would leave `apply` never returning at all.
#   ASK, never assume: hba_file may live inside PGDATA (every stock container
#   image) or under a distribution config dir, and editing the wrong copy is a
#   change that verifies green on disk and changes nothing at all.
pg_hba_file_path() {
    local mode="$1" container="$2" host="$3" user="$4" port="$5"
    local out="" rc=0 sink=""
    sink="$(pg_err_sink)"
    out="$(pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" pg_run_client \
        "$mode" "$container" "$host" "$user" "$port" \
        psql -d postgres -tAqc 'SHOW hba_file' 2>"$sink")" || rc=$?
    [[ "$rc" -eq 0 ]] || return 3
    out="${out%%$'\n'*}"
    out="${out#"${out%%[![:space:]]*}"}"
    out="${out%"${out##*[![:space:]]}"}"
    [[ "$out" == /* ]] || return 3
    printf '%s\n' "$out"
    return 0
}
