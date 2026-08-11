#!/usr/bin/env bash
# 48-db-local-auth.sh - let Odoo reach the DECLARED role on a local developer
# cluster without a password, by adding one narrow rule to that cluster's
# pg_hba.conf. No credential is stored anywhere, by the plugin or by the user.
#
# Every odoo-bin run opens a connection to the maintenance database before any
# module loads, so a cluster that refuses that connection blocks init, update and
# test alike - not just a create. This step removes the refusal at its source for
# a cluster you control, and REFUSES for one you do not.
#
# Subcommands:
#   describe                                 One-line description.
#   check  [--series X.Y] [--profile P]      Read-only. Per declared instance, ask
#                                            whether Odoo can authenticate (the
#                                            same host-side preflight `apply`
#                                            verifies with). Exit 1 when at least
#                                            one instance is PROVEN denied - the
#                                            one state this step remedies.
#                                            `unreachable` and undeterminable are
#                                            reported and do NOT mark the step as
#                                            needed: this step cannot start a
#                                            cluster, and undeterminable is never
#                                            read as a yes OR as a no.
#   apply  [--series X.Y] [--profile P]      Enable it. Probes privilege first,
#                                            backs up, edits, reloads, verifies.
#   revert [--series X.Y] [--profile P]      Remove the managed block and reload.
#   With no --series, every declared instance is processed.
#
# CONFIG (env overrides):
#   ODOO_AI_HOME       machine-global state dir      (default $HOME/.odoo-ai)
#   ODOO_AI_INSTANCES  full-path override for instances.toml
#   ODOO_AI_BACKUP_TS  fixed timestamp for deterministic test backups (optional)
#   ODOO_PG_PASSWORD   not used here. It is the ALTERNATIVE this step names when a
#                      cluster cannot be reconfigured.
#
# HARD RULES:
#   - The rule is narrow on BOTH axes it can be narrowed on:
#     `host all <declared db_user> <discovered-addr>/32 trust`. One /32 (or /128),
#     never a subnet; the declared role, never `all`. `database` stays `all`
#     because ephemeral database names are minted at runtime and the maintenance
#     database must stay reachable.
#   - The address is DISCOVERED per container and never assumed. A published-port
#     connection arrives from the bridge gateway, not from loopback, and that
#     gateway differs between networks on one machine.
#   - REFUSES rather than guesses. No address, no docker, no write access, or a
#     port published on anything but a loopback address: nothing is written.
#   - NEVER runs sudo, and there is no flag that makes it. The native arm PRINTS
#     the exact block, path and reload command, then refuses.
#   - NEVER writes instances.toml, and never writes a password anywhere.
#   - NEVER reports success without reconnecting: only a host-side
#     `odoo_db.py preflight` reporting DB_AUTH=ok can make `apply` exit 0.
#   - The cluster's own questions (SHOW hba_file, pg_hba_file_rules,
#     pg_reload_conf) are superuser-restricted, so they are asked as a role the
#     cluster CONFIRMED is a superuser, over the container-local socket the stock
#     image already trusts. No credential is used and none is stored.
#   - The write COMMITS only when the container has counted the bytes it received
#     and they match: the bound kills the local docker client, not the process
#     inside the container, so a partial stream must be unable to rename itself
#     over a live pg_hba.conf. A failed write NEVER asserts the file's state - it
#     re-reads it and reports what is actually there.
#   - Which arm applies is decided by where the SERVER runs, not by db_run_mode
#     (which describes this host's CLIENT surface) - see _container_publishing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$SCRIPT_DIR/../lib"
INSTANCES_IO="$LIB_DIR/instances_io.py"
HBA_EDIT="$LIB_DIR/pg_hba_edit.py"
ODOO_DB_PY="$LIB_DIR/odoo_db.py"

# Client-surface dispatch + the bounded-probe helper + the address-discovery
# ladder. Every question this step asks of docker or of the server goes through
# there, so "could not ask" can never become an answer.
# shellcheck source=../lib/pg_mode.sh
source "$LIB_DIR/pg_mode.sh"
# shellcheck source=../lib/resolve_instances.sh
source "$LIB_DIR/resolve_instances.sh"
INSTANCES_TOML="$(_resolve_instances)"

SETUP_CMD="/odoo-ai-agents:odoo-setup"

cmd_describe() {
    echo "Let Odoo reach the declared PostgreSQL role without a password, from this host only"
}

# ---------------------------------------------------------------------------
# _enumerate_instance_keys <toml>
#   TAB-separated `series<TAB>profile` for EVERY declared instance, whatever its
#   run_mode: db_run_mode describes POSTGRES, so a compose-run Odoo still has a
#   cluster whose pg_hba.conf this step may own.
# ---------------------------------------------------------------------------
_enumerate_instance_keys() {
    local toml="$1"
    [[ -f "$toml" && -f "$INSTANCES_IO" ]] || return 0
    python3 - "$toml" "$LIB_DIR" <<'PY' 2>/dev/null || true
import sys
toml, libdir = sys.argv[1], sys.argv[2]
sys.path.insert(0, libdir)
import instances_io
for it in instances_io.load_instances(toml):
    series = instances_io.series_of(it)
    if not series:
        continue
    print("\t".join([series, instances_io.profile_of(it) or ""]))
PY
}

# ---------------------------------------------------------------------------
# _load_instance <series> <profile>
#   eval the instance's declared facts into INST_* in the CALLER's scope.
#   Returns 1 when the block cannot be read - the caller must then refuse, never
#   substitute a default for a fact the catalog was supposed to declare.
# ---------------------------------------------------------------------------
_load_instance() {
    local series="$1" profile="${2:-}" kv=""
    kv="$(python3 "$INSTANCES_IO" read "$INSTANCES_TOML" "$series" "$profile" 2>/dev/null)" || return 1
    [[ -n "$kv" ]] || return 1
    eval "$kv" || return 1
    return 0
}

_label() {
    local series="$1" profile="${2:-}"
    [[ -n "$profile" ]] && { printf '%s:%s\n' "$series" "$profile"; return 0; }
    printf '%s\n' "$series"
}

# ---------------------------------------------------------------------------
# Rung 3 - the ONLY rung that may permit exit 0.
#
# Runs the preflight PRIMITIVE from the host, under the instance's own declared
# interpreter, over Odoo's own connection resolution: the exact route every build
# takes. Rungs 1 and 2 read the server's opinion of its own configuration and can
# only ever explain a failure; this one reproduces the thing that was failing.
#
# odoo_db.py OWNS the refusal text - its stderr is forwarded verbatim, never
# re-worded, so there is exactly one copy of the verdict in the whole plugin.
#   exit: 0 DB_AUTH=ok | 8 denied | 9 unreachable | anything else NOT PROVEN.
# 1 (undeterminable) and 10 (that venv cannot import odoo) are NEVER read as ok.
# ---------------------------------------------------------------------------
_preflight_from_host() {
    local py="$1" host="$2" user="$3" port="$4" root="$5"
    [[ -n "$py" && -x "$py" && -f "$ODOO_DB_PY" ]] || return 20
    local -a args=("$ODOO_DB_PY" preflight --db-host "$host" --db-user "$user")
    [[ -n "$root" ]] && args+=(--odoo-root "$root")
    [[ -n "$port" ]] && args+=(--db-port "$port")
    local rc=0
    pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" "$py" "${args[@]}" >/dev/null || rc=$?
    return "$rc"
}

# _psql_scalar <mode> <container> <host> <user> <port> <sql>
#   stdout: the single value the query returned; exit non-zero when it could not
#   be asked. Bounded, and it runs INSIDE the container for docker mode, over the
#   container-local socket the stock image already trusts - so it works on exactly
#   the cluster whose host-side TCP is refusing us.
#   The server's own error line is left on pg_mode.sh's pg_err channel, so the
#   caller can ask pg_err_denied afterwards. Several of the questions this step asks
#   (pg_reload_conf, pg_hba_file_rules, SHOW hba_file) are superuser-restricted, and
#   "the cluster does not have it" is a different fact from "this role may not ask" -
#   reporting the first for the second sends the reader to upgrade a cluster that is
#   already new enough. The channel is a FILE because every one of these calls
#   happens inside a command substitution, and a subshell cannot hand a variable
#   back.
_psql_scalar() {
    local mode="$1" container="$2" host="$3" user="$4" port="$5" sql="$6"
    local out="" rc=0 sink=""
    sink="$(pg_err_sink)"
    out="$(pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" pg_run_client \
        "$mode" "$container" "$host" "$user" "$port" \
        psql -d postgres -tAqc "$sql" 2>"$sink")" || rc=$?
    [[ "$rc" -eq 0 ]] || return 1
    out="${out%%$'\n'*}"
    printf '%s\n' "$out"
    return 0
}

# ---------------------------------------------------------------------------
# _cluster_superuser <container> <declared-role>
#   stdout: the role this step asks the CLUSTER's own questions as, and exit 0
#           always (a name is always emitted). Sets _SU_PROVEN=1 only when that
#           role was OBSERVED to be a superuser.
#
#   Why this exists: `pg_reload_conf()`, `pg_hba_file_rules` and `SHOW hba_file`
#   are all superuser-restricted by default, while the DECLARED db_user is
#   routinely a plain `LOGIN CREATEDB` role - which is the correct way to
#   provision an Odoo role and exactly this step's target. Asking as that role
#   left the cluster half-configured: the file was rewritten, the reload was
#   refused with "permission denied for function", and the remedy named the same
#   powerless role, run after run.
#   The candidate list is DATA-DRIVEN - the image's own POSTGRES_USER first, then
#   the conventional `postgres`, then the declared role - and each candidate is
#   CONFIRMED by asking the server whether it is a superuser, never assumed. This
#   is safe because it runs over the container-local socket, which the stock image
#   already trusts; no credential is used and none is stored.
# ---------------------------------------------------------------------------
_cluster_superuser() {
    local container="$1" declared="$2"
    local env_user="" cand="" answer="" tried=""
    _SU_PROVEN=0
    env_user="$(pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" docker inspect "$container" \
        --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
        | sed -n 's/^POSTGRES_USER=//p' | head -n 1)" || env_user=""
    for cand in "$env_user" postgres "$declared"; do
        [[ -n "$cand" ]] || continue
        case "
$tried" in *"
$cand
"*) continue ;; esac
        tried="$tried$cand
"
        answer="$(_psql_scalar docker "$container" "" "$cand" "" \
            "SELECT rolsuper FROM pg_roles WHERE rolname = current_user")" || continue
        if [[ "$answer" == "t" ]]; then
            _SU_PROVEN=1
            printf '%s\n' "$cand"
            return 0
        fi
    done
    printf '%s\n' "$declared"
    return 0
}

# ---------------------------------------------------------------------------
# The refusal for a cluster that cannot be reconfigured from here.
# tcp-only DECLARES that this host has no client surface for the cluster; a
# managed or remote cluster is the same fact arrived at differently. Naming
# ODOO_PG_PASSWORD here is what keeps the refusal a first-class path rather than
# a dead end.
# ---------------------------------------------------------------------------
_refuse_unreconfigurable() {
    local label="$1" mode="${2:-<absent>}"
    echo "x $label: db_run_mode=$mode declares no client surface on this host, so this" >&2
    echo "  cluster cannot be reconfigured from here. Nothing was written." >&2
    echo "  For a managed or remote cluster that is the correct outcome: export" >&2
    echo "  ODOO_PG_PASSWORD=... instead (this shell only; never stored by the plugin)." >&2
    echo "  If the cluster DOES run in a container on this host, declare its surface" >&2
    echo "  first: run $SETUP_CMD, then re-run this step." >&2
}

# ---------------------------------------------------------------------------
# The native arm: ADVISE ONLY, with no opt-in that changes that.
#
# Writing under a system cluster's config directory needs root, and this plugin
# never runs sudo. It is also the arm no observation covers - the machine this was
# built on has PostgreSQL in containers only - so shipping code that edits a
# system file through a path nobody has exercised would be worse than printing
# the two lines a human can check first.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# _container_publishing <db_port>
#   stdout: the name of the ONE running container publishing <db_port>.
#   exit:   0 a name was emitted | 1 none, ambiguous, or docker could not be
#           asked - all three mean "do not route to the container arm".
#
#   db_run_mode answers "which CLIENT surface does this host have", and pg_mode.sh
#   deliberately prefers `native` whenever the libpq binaries are on PATH. That
#   says NOTHING about where the SERVER runs: `postgresql-client` installed plus
#   PostgreSQL in a container publishing a loopback port is the modal developer
#   host, and it records db_run_mode=native. Branching the FIX on that fact sent
#   such a host to the advisory arm, which prints trust rules for 127.0.0.1 - the
#   rule pg_mode.sh's own header calls already present in the stock image and
#   already dead, because a host-side connection to a published port re-originates
#   from the bridge gateway. `check` then returned 1 forever and setup stopped
#   being idempotent. So the SERVER's location is asked separately, here.
# ---------------------------------------------------------------------------
_container_publishing() {
    local port="${1:-}" names="" line
    [[ -n "$port" ]] || return 1
    _pg_mode_have docker || return 1
    names="$(_pg_mode_container_names "$port")" || return 1
    local -a hits=()
    while IFS= read -r line; do
        [[ -n "$line" ]] && hits+=("$line")
    done <<<"$names"
    case "${#hits[@]}" in
        1) printf '%s\n' "${hits[0]}"; return 0 ;;
        0) return 1 ;;
        *) echo "  note: ${#hits[@]} containers publish port ${port} (${hits[*]}) - refusing to" >&2
           echo "  guess which one serves this instance. Declare db_container on the" >&2
           echo "  [[instance]] to use the container arm." >&2
           return 1 ;;
    esac
}

_native_advice() {
    local label="$1" user="$2" host="$3" port="$4"
    local hba="" block=""
    hba="$(pg_hba_file_path native "" "$host" "$user" "$port" 2>/dev/null)" || hba=""
    # No NAT hop stands between this host and a native cluster, so the connection
    # presents loopback directly - both families, because which one a declared
    # db_host resolves to is the resolver's business, not this step's.
    block="$(python3 "$HBA_EDIT" render --user "$user" \
        --address "127.0.0.1/32" --address "::1/128" 2>/dev/null)" || {
        echo "x $label: could not render the rule for role '$user'. Nothing was written." >&2
        return 1
    }
    echo "-- $label: native cluster - ADVISE ONLY, nothing was written --"
    echo "  Add the line for the address family your db_host resolves to, ABOVE the"
    echo "  file's first rule line (pg_hba.conf is first-match-wins, so a line added"
    echo "  at the end can never match):"
    # printf '%s\n', not '%s': command substitution strips the block's trailing
    # newline, so the un-terminated form glued the next line onto the END marker -
    # the reader was handed a "File:" path they could not see.
    printf '%s\n' "$block" | sed 's/^/    /'
    if [[ -n "$hba" ]]; then
        echo "  File: $hba"
    else
        echo "  File: run 'psql -tAqc \"SHOW hba_file\"' as a superuser to get its path."
        if pg_err_denied; then
            echo "        (this step could not ask: 'SHOW hba_file' is superuser-only and"
            echo "         role '$user' is not one - the cluster answered, so it is running.)"
        fi
    fi
    echo "  Then reload without restarting:"
    echo "    psql -d postgres -c 'SELECT pg_reload_conf()'"
    echo "  Then re-run $SETUP_CMD to verify by reconnecting."
    # The same alternative the unreconfigurable arm names. Without it, whether a
    # reader is handed a usable answer depended on whether `psql` happens to be
    # installed - and for a remote or managed cluster reached by a native client,
    # hand-editing a file on another machine is not the answer they need.
    echo "  For a cluster you do not administer (remote or managed), do this instead:"
    echo "    export ODOO_PG_PASSWORD=...   # this shell only; never stored by the plugin"
    echo "x $label: this step does not edit a system file and never runs sudo." >&2
    return 1
}

# ---------------------------------------------------------------------------
# _hba_backup_path <mode> <container> <hba>
#   Echo a backup path that does NOT yet exist. An existing backup is never
#   overwritten: the first one is the state the cluster was in before this plugin
#   ever touched it, and that is the one worth keeping.
# ---------------------------------------------------------------------------
_hba_backup_path() {
    local mode="$1" container="$2" hba="$3"
    local ts="${ODOO_AI_BACKUP_TS:-}"
    [[ -n "$ts" ]] || ts="$(date -u +%Y%m%dT%H%M%SZ)"
    local base="${hba}.odoo-ai.${ts}.bak" cand="" n=0
    while [[ "$n" -lt 50 ]]; do
        if [[ "$n" -eq 0 ]]; then cand="$base"; else cand="${base}.${n}"; fi
        if ! _container_exists_path "$mode" "$container" "$cand"; then
            printf '%s\n' "$cand"
            return 0
        fi
        n=$((n + 1))
    done
    echo "x 50 backups already exist for $hba - refusing to add another." >&2
    return 1
}

# _container_exists_path <mode> <container> <path> -> 0 when the path exists
_container_exists_path() {
    local mode="$1" container="$2" path="$3"
    case "$mode" in
        docker) pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
                    docker exec "$container" test -e "$path" >/dev/null 2>&1 ;;
        *) [[ -e "$path" ]] ;;
    esac
}

# ---------------------------------------------------------------------------
# _write_hba_atomically <container> <hba> <new-content-file>
#   Copy the ORIGINAL to a sibling temp first (`cp -p`, so the temp carries the
#   original's mode and owner BEFORE any content exists), overwrite that temp's
#   contents, VERIFY the temp's byte count against the source's, and only then
#   rename it over the target. The rename is within one directory, therefore one
#   filesystem, therefore atomic.
#   Only cp / cat / wc / mv / rm run in the container; all of them exist in any
#   Debian-based PostgreSQL image.
#
#   The byte count is the load-bearing part, not a belt. The rename is atomic
#   against a CRASH but NOT against this step's own BOUND: when the bound elapses,
#   `timeout` kills the local `docker exec` CLIENT, and docker does NOT kill the
#   process it exec'd inside the container (moby#9098). The in-container `cat`
#   then sees EOF on the broken stream, exits 0 with a PARTIAL file, and `mv`
#   COMMITS it - a truncated pg_hba.conf on a running cluster, which the
#   postmaster then refuses to start on, while the host side reported failure and
#   claimed the original was intact. Comparing the byte count on the CONTAINER
#   side is what makes a partial stream unable to commit even when nobody is left
#   on the host to notice.
# ---------------------------------------------------------------------------
_write_hba_atomically() {
    local container="$1" hba="$2" src="$3" want=""
    want="$(wc -c <"$src" | tr -d '[:space:]')" || return 1
    [[ -n "$want" ]] || return 1
    pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" docker exec -i "$container" sh -c '
        f="$1"; want="$2"; t="$f.odoo-ai.tmp"
        cp -p "$f" "$t" || { rm -f "$t"; exit 1; }
        cat > "$t" || { rm -f "$t"; exit 1; }
        got="$(wc -c < "$t" | tr -d "[:space:]")"
        if [ "$got" != "$want" ]; then
            echo "pg_hba write REFUSED in-container: got $got of $want bytes" >&2
            rm -f "$t"; exit 1
        fi
        mv "$t" "$f" || { rm -f "$t"; exit 1; }
    ' _ "$hba" "$want" <"$src"
}

# ---------------------------------------------------------------------------
# _report_write_outcome <container> <hba> <pre> <intended> <backup>
#   A failed write does NOT prove the file is untouched - see the moby note above:
#   the in-container writer can still commit after the host gave up. So the file
#   is RE-READ and compared, and the report states which of the four possible
#   states the cluster is actually in. Asserting "the original is intact" without
#   looking is the one thing that must never happen here, because the operator
#   would have to disbelieve the message to find the damage.
#   Always returns 1: whatever the state, this apply did not earn a success.
# ---------------------------------------------------------------------------
_report_write_outcome() {
    local container="$1" hba="$2" pre="$3" intended="$4" bak="$5"
    local after="${pre}.after"
    if ! pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
            docker exec "$container" cat "$hba" >"$after" 2>/dev/null; then
        echo "x $container: could not write $hba, and the file could not be re-read" >&2
        echo "  either - so whether it changed is UNKNOWN. Compare it against the" >&2
        echo "  backup at $bak before restarting this cluster: a partially written" >&2
        echo "  pg_hba.conf is a file the postmaster refuses to start on." >&2
        return 1
    fi
    if cmp -s "$after" "$pre"; then
        echo "x $container: could not write $hba. Re-read CONFIRMS the file is" >&2
        echo "  unchanged, byte for byte; the backup at $bak is still the same content." >&2
    elif cmp -s "$after" "$intended"; then
        echo "x $container: the write reported failure but the file on the cluster now" >&2
        echo "  carries EXACTLY the intended content - the in-container writer committed" >&2
        echo "  after this step stopped waiting for it. Nothing is truncated. The running" >&2
        echo "  server has NOT re-read it, so re-run this step: it will see the block" >&2
        echo "  already present, take no backup, and only reload." >&2
    else
        echo "x $container: $hba matches NEITHER its pre-edit content NOR the intended" >&2
        echo "  content - it is PARTIALLY WRITTEN. Restore it from $bak before this" >&2
        echo "  cluster is restarted; the postmaster refuses to start on a pg_hba.conf" >&2
        echo "  it cannot parse, and until then the running server keeps its old rules." >&2
    fi
    return 1
}

# ---------------------------------------------------------------------------
# _pgdata_mount_report <container> <hba>
#   Say whether the edit survives container recreation, based on what the
#   container actually declares - never on a claim of durability. hba_file lives
#   inside PGDATA on a stock image, so the answer is the mount type covering it.
# ---------------------------------------------------------------------------
_pgdata_mount_report() {
    local container="$1" hba="$2"
    local raw=""
    # BOUNDED like every other question asked of docker here: a daemon that wedges
    # after the earlier probes succeeded must not leave `apply` never returning.
    raw="$(pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" docker inspect "$container" \
        --format '{{range .Mounts}}{{.Type}} {{.Destination}} {{.Name}}
{{end}}' 2>/dev/null)" || {
        echo "  durability: could not be asked (docker inspect failed)."
        return 0
    }
    local line type dest name best_type="" best_dest="" best_name=""
    while IFS= read -r line; do
        [[ -n "$line" ]] || continue
        type="${line%% *}"; line="${line#* }"
        dest="${line%% *}"; name="${line#* }"
        case "$hba" in
            "$dest"/*|"$dest")
                if [[ "${#dest}" -gt "${#best_dest}" ]]; then
                    best_type="$type"; best_dest="$dest"; best_name="$name"
                fi ;;
        esac
    done <<<"$raw"
    case "$best_type" in
        volume) echo "  durability: PGDATA is the named volume '${best_name}', so this edit"
                echo "    SURVIVES 'docker rm' and '--force-recreate'. It does NOT survive"
                echo "    deleting the volume ('compose down -v', 'docker volume rm')." ;;
        bind)   echo "  durability: PGDATA is a bind mount from '${best_name}', so this edit"
                echo "    survives container recreation while that path is reused." ;;
        "")     echo "  durability: no mount covers $hba, so it lives in the image layer -"
                echo "    this edit is LOST the moment the container is recreated. 'check'"
                echo "    detects that on the next setup run and re-applies." ;;
        *)      echo "  durability: PGDATA is a '${best_type}' mount; survival across a"
                echo "    recreate depends on that mount being reused." ;;
    esac
}

# ---------------------------------------------------------------------------
# check - read-only, no prompt, no privilege.
#
# Asks rung 3 for every declared instance. Exit 1 ONLY on a proven `denied`: that
# is the state this step remedies, and it is what makes an edit lost to volume
# deletion self-heal on the next setup run. `unreachable` and undeterminable are
# reported and do NOT mark the step as needed - this step cannot start a cluster,
# and an undeterminable answer is never read as a yes OR as a no.
# ---------------------------------------------------------------------------
cmd_check() {
    local want_series="" want_profile=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) want_series="$2"; shift 2 ;;
            --profile) want_profile="$2"; shift 2 ;;
            *) echo "Unknown argument: $1" >&2; return 2 ;;
        esac
    done
    [[ -f "$INSTANCES_TOML" ]] || return 0
    local series profile label rc=0 need=0 any=0
    while IFS=$'\t' read -r series profile; do
        [[ -n "$series" ]] || continue
        [[ -z "$want_series" || "$series" == "$want_series" ]] || continue
        [[ -z "$want_profile" || "$profile" == "$want_profile" ]] || continue
        any=1
        label="$(_label "$series" "$profile")"
        if ! _load_instance "$series" "$profile"; then
            echo "  [ ?? ] $label: its [[instance]] block could not be read."
            continue
        fi
        rc=0
        # A SURVEY line per instance, so the owned refusal block is not repeated
        # once per declared instance here; `apply` forwards those bytes verbatim,
        # where they are actionable. Same division 05-prereq-check.sh already uses.
        _preflight_from_host "${INST_PYTHON:-}" "${INST_DB_HOST:-localhost}" \
            "${INST_DB_USER:-odoo}" "${INST_DB_PORT:-}" "${INST_ODOO_ROOT:-}" \
            2>/dev/null || rc=$?
        case "$rc" in
            0)  echo "  [ok ] $label: Odoo can authenticate without a stored password" ;;
            8)  echo "  [ -- ] $label: authentication is REFUSED - every build refuses before"
                echo "         launch. This step's 'apply' is what fixes it."
                need=1 ;;
            9)  echo "  [ -- ] $label: the cluster did not answer at all. Start it first;"
                echo "         this step cannot start a cluster." ;;
            20) echo "  [ ?? ] $label: no runnable 'python' is declared, so Odoo's own"
                echo "         connection cannot be tested. fix: 45-venv.sh record-env" ;;
            *)  echo "  [ ?? ] $label: undeterminable (exit $rc) - read as neither a yes nor"
                echo "         a no. fix: 45-venv.sh record-env --series $series" ;;
        esac
    done < <(_enumerate_instance_keys "$INSTANCES_TOML")
    [[ "$any" -eq 1 ]] || return 0
    [[ "$need" -eq 0 ]] || return 1
    return 0
}

# ---------------------------------------------------------------------------
# _apply_one_cluster <container> <hba> <superuser> <users...> - the mutating stages.
#
# Order: probe (already done by the caller) -> read -> transform -> back up ->
# rename -> reload. The transform is a PURE host-side text filter that touches
# nothing, so running it before the backup keeps the only invariant that matters -
# a backup exists before the RENAME - while letting an unchanged file skip both.
# Without that, every idempotent re-run of setup would leave one more backup
# behind forever.
# ---------------------------------------------------------------------------
_apply_one_cluster() {
    local container="$1" hba="$2" su="$3"; shift 3
    local -a users=("$@")
    local -a addrs=()
    local line
    while IFS= read -r line; do
        [[ -n "$line" ]] && addrs+=("$line")
    done < <(pg_origin_address "$container")
    if [[ "${#addrs[@]}" -eq 0 ]]; then
        echo "x $container: the address this host's connections arrive from could not be" >&2
        echo "  discovered, so no rule was written. A guessed gateway would authorise a" >&2
        echo "  stranger and still leave Odoo refused. fix: run $SETUP_CMD once docker can" >&2
        echo "  answer for this container." >&2
        return 1
    fi

    local tmpdir cur new
    tmpdir="$(mktemp -d)"
    cur="$tmpdir/cur"; new="$tmpdir/new"
    if ! pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
            docker exec "$container" cat "$hba" >"$cur" 2>/dev/null; then
        echo "x $container: could not read $hba. NOTHING was changed." >&2
        rm -rf "$tmpdir"; return 1
    fi
    local -a edit=("$HBA_EDIT" apply --file "$cur")
    local u a
    for u in "${users[@]}"; do edit+=(--user "$u"); done
    for a in "${addrs[@]}"; do edit+=(--address "$a"); done
    if ! python3 "${edit[@]}" >"$new"; then
        echo "x $container: the rule was REFUSED (see above). NOTHING was changed." >&2
        rm -rf "$tmpdir"; return 1
    fi
    if cmp -s "$cur" "$new"; then
        echo "  $container: pg_hba.conf already carries exactly this managed block"
    else
        local bak=""
        bak="$(_hba_backup_path docker "$container" "$hba")" || { rm -rf "$tmpdir"; return 1; }
        if ! pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
                docker exec "$container" cp -p "$hba" "$bak" >/dev/null 2>&1; then
            echo "x $container: could not back up $hba. NOTHING was changed." >&2
            rm -rf "$tmpdir"; return 1
        fi
        echo "  backup -> $container:$bak (an existing backup is never overwritten)"
        if ! _write_hba_atomically "$container" "$hba" "$new"; then
            # NEVER assert the file's state here - ASK it. See _report_write_outcome.
            _report_write_outcome "$container" "$hba" "$cur" "$new" "$bak" || true
            rm -rf "$tmpdir"; return 1
        fi
        echo "  wrote managed block into $container:$hba"
    fi
    printf '  rule(s) now in the managed block:\n'
    sed -n "/^# BEGIN odoo-ai-agents/,/^# END odoo-ai-agents/p" "$new" | sed 's/^/    /'
    rm -rf "$tmpdir"

    # Reload, never restart: pg_reload_conf() makes the running server re-read the
    # file, so a live cluster with open connections is never interrupted.
    # Asked as the SUPERUSER the cluster itself named (see _cluster_superuser):
    # pg_reload_conf() is superuser-restricted, and the declared Odoo role usually
    # is not one - asking as it left the file rewritten and the server never told.
    _APPLY_ADDRS="${addrs[*]}"
    if ! _psql_scalar docker "$container" "" "$su" "" \
            "SELECT pg_reload_conf()" >/dev/null; then
        echo "x $container: the file was written but the reload could not be asked for, so" >&2
        echo "  the running server is still using the OLD rules." >&2
        if pg_err_denied; then
            echo "  cause: role '$su' is not PERMITTED to call pg_reload_conf() - it is" >&2
            echo "  superuser-only, and no superuser role could be confirmed on this" >&2
            echo "  cluster. Reload as one by hand, or export ODOO_PG_PASSWORD=... and" >&2
            echo "  leave this cluster's rules alone." >&2
        fi
        echo "  Reload by hand:" >&2
        echo "    docker exec $container psql -U <superuser> -d postgres -c 'SELECT pg_reload_conf()'" >&2
        return 1
    fi
    echo "  reloaded $container (pg_reload_conf, no restart, no dropped connection)"
    return 0
}

# ---------------------------------------------------------------------------
# _verify_cluster_rungs <container> <superuser> <user> <addr-list> <baseline-errors>
#   Rungs 1 and 2 (A.7): the file still PARSES no worse than before, and the
#   server PARSES the managed line without error. Both are read from
#   pg_hba_file_rules, which exists on PostgreSQL 10+ and is superuser-restricted;
#   a rung that cannot be run is SKIPPED, said to be skipped, and says WHICH of
#   the two reasons applies - "this cluster does not have the view" sends a reader
#   to upgrade a cluster that is already new enough.
#
#   WHAT RUNG 2 DOES NOT PROVE: pg_hba_file_rules re-reads and re-parses hba_file
#   FROM DISK at query time; it never reports the ruleset the postmaster currently
#   has LOADED. So it cannot distinguish a reload that happened from one that did
#   not, and its value is narrower than it looks - it confirms the server can read
#   OUR line and agrees it is well-formed. Rung 3 (reconnecting over Odoo's own
#   connection) is the only check that observes the loaded ruleset, which is why it
#   is the only one that may permit exit 0.
# ---------------------------------------------------------------------------
_verify_cluster_rungs() {
    local container="$1" su="$2" user="$3" addrs="$4" baseline="$5"
    local errs=""
    if ! errs="$(_psql_scalar docker "$container" "" "$su" "" \
            "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL")"; then
        if pg_err_denied; then
            echo "  rung 1 SKIPPED: role '$su' is not PERMITTED to read pg_hba_file_rules"
            echo "         (superuser-only) - the view exists, this role may not read it"
            echo "  rung 2 SKIPPED: same reason - so the parse-error regression check and"
            echo "         the read-back are both unavailable. Rung 3 still decides."
        else
            echo "  rung 1 SKIPPED: pg_hba_file_rules is not available on this cluster"
            echo "         (it exists from PostgreSQL 10)"
            echo "  rung 2 SKIPPED: same reason - the rule cannot be read back from the server"
        fi
        return 0
    fi
    if [[ -n "$baseline" && "$errs" -gt "$baseline" ]]; then
        echo "x $container: the edited pg_hba.conf has $errs parse error(s), up from" >&2
        echo "  $baseline before the edit. Revert with: $(basename "$0") revert" >&2
        return 1
    fi
    echo "  rung 1 ok: pg_hba.conf parse errors $errs (baseline $baseline)"
    local a live=""
    for a in $addrs; do
        live="$(_psql_scalar docker "$container" "" "$su" "" \
            "SELECT count(*) FROM pg_hba_file_rules WHERE type = 'host'
               AND auth_method = 'trust' AND address = '${a%%/*}'
               AND '$user' = ANY(user_name)")" || live=""
        if [[ -z "$live" || "$live" -lt 1 ]]; then
            echo "x $container: the server does not parse a trust rule for role '$user' at" >&2
            echo "  ${a%%/*} out of the file it reads, so the bytes this step wrote are not" >&2
            echo "  the rule it needed to write. Revert with:" >&2
            echo "  $(basename "$0") revert" >&2
            return 1
        fi
    done
    echo "  rung 2 ok: the server parses the managed rule(s) for role '$user' from the file"
    echo "         (this reads the FILE, not the loaded ruleset - rung 3 checks that)"
    return 0
}

# ---------------------------------------------------------------------------
# _bad_cluster <container> - this cluster was refused or failed.
#
# Assigns into cmd_apply's own `failed` / `bad_clusters` (bash scopes
# dynamically), so every refusal arm records the SAME two facts. Without the
# second one, rung 3 would still run for an instance whose cluster was never
# touched, and a cluster that authenticates for some other reason would print
# `rung 3 ok` directly under a refusal - a green line the run did not earn.
# ---------------------------------------------------------------------------
_bad_cluster() {
    failed=1
    bad_clusters="${bad_clusters}${1}
"
}

# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------
cmd_apply() {
    local want_series="" want_profile=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) want_series="$2"; shift 2 ;;
            --profile) want_profile="$2"; shift 2 ;;
            *) echo "Unknown argument: $1" >&2; return 2 ;;
        esac
    done
    [[ -f "$INSTANCES_TOML" ]] || {
        echo "x no instance catalog at $INSTANCES_TOML - declare an instance first:" >&2
        echo "  run $SETUP_CMD." >&2
        return 1
    }
    [[ -f "$HBA_EDIT" ]] || {
        echo "x $HBA_EDIT is missing - the plugin is only partially installed." >&2
        return 1
    }

    # PASS 1 - group the SELECTED instances by cluster, so a cluster shared by two
    # declared roles gets ONE block with one narrow line per role. Applying per
    # instance instead would rewrite the block each time and silently drop the
    # other role's line.
    local series profile label
    local -a sel_series=() sel_profile=() sel_container=()
    local groups="" failed=0 bad_clusters="" eff_container=""
    while IFS=$'\t' read -r series profile; do
        [[ -n "$series" ]] || continue
        [[ -z "$want_series" || "$series" == "$want_series" ]] || continue
        [[ -z "$want_profile" || "$profile" == "$want_profile" ]] || continue
        label="$(_label "$series" "$profile")"
        if ! _load_instance "$series" "$profile"; then
            echo "x $label: its [[instance]] block could not be read. Skipped." >&2
            continue
        fi
        # The EFFECTIVE cluster for this instance: a container name when the SERVER
        # runs in one (whatever db_run_mode says about this host's CLIENT surface),
        # and empty when it does not. Every later pass keys off this, so the routing
        # decision is made once, here, instead of being re-derived from
        # db_run_mode in three places that could then disagree.
        eff_container=""
        case "${INST_DB_RUN_MODE:-}" in
            docker)
                if [[ -z "${INST_DB_CONTAINER:-}" ]]; then
                    echo "x $label: db_run_mode=docker but db_container is not declared, so" >&2
                    echo "  there is no named cluster to reconfigure and nothing was written." >&2
                    echo "  fix: run $SETUP_CMD to re-derive db_container. Immediate" >&2
                    echo "  alternative: export ODOO_PG_PASSWORD=... for this shell." >&2
                    failed=1
                else
                    eff_container="${INST_DB_CONTAINER}"
                fi ;;
            native)
                # A native CLIENT does not mean a native SERVER - see
                # _container_publishing. When a container publishes the declared
                # port, the container arm is the only one that can fix this
                # instance, so it is taken.
                if eff_container="$(_container_publishing "${INST_DB_PORT:-}")" \
                        && [[ -n "$eff_container" ]]; then
                    echo "-- $label: db_run_mode=native (libpq client on PATH), but the SERVER is"
                    echo "   container '$eff_container', which publishes port ${INST_DB_PORT}."
                    echo "   Using the container arm: a host-side connection to a published port"
                    echo "   arrives from that container's bridge gateway, so a loopback trust"
                    echo "   rule would change nothing."
                else
                    eff_container=""
                    _native_advice "$label" "${INST_DB_USER:-odoo}" \
                        "${INST_DB_HOST:-localhost}" "${INST_DB_PORT:-}" || failed=1
                fi ;;
            *)
                _refuse_unreconfigurable "$label" "${INST_DB_RUN_MODE:-}"
                failed=1 ;;
        esac
        sel_series+=("$series"); sel_profile+=("$profile")
        sel_container+=("$eff_container")
        if [[ -n "$eff_container" ]]; then
            groups="$groups${eff_container}"$'\t'"${INST_DB_USER:-odoo}"$'\n'
        fi
    done < <(_enumerate_instance_keys "$INSTANCES_TOML")

    if [[ -n "$want_series" && "${#sel_series[@]}" -eq 0 ]]; then
        echo "x no [[instance]] declared for series $want_series." >&2
        return 1
    fi

    # PASS 2 - one cluster at a time: probe privilege and safety FIRST, non-
    # mutatingly, then edit. Nothing below the probe block can be reached without
    # the probes passing, which is what makes "refuse, never half-apply" true.
    local containers="" c users u hba baseline rc=0 su=""
    containers="$(printf '%s' "$groups" | cut -f1 | sort -u)"
    while IFS= read -r c; do
        [[ -n "$c" ]] || continue
        users="$(printf '%s' "$groups" | awk -F'\t' -v c="$c" '$1==c {print $2}' | sort -u)"
        local -a ulist=()
        while IFS= read -r u; do [[ -n "$u" ]] && ulist+=("$u"); done <<<"$users"
        echo "-- cluster $c (role(s): ${ulist[*]}) --"

        if ! _pg_mode_have docker; then
            echo "x docker is not on PATH, so container $c cannot be reached. Nothing was" >&2
            echo "  written. fix: install docker, then run $SETUP_CMD. Immediate" >&2
            echo "  alternative: export ODOO_PG_PASSWORD=... for this shell." >&2
            _bad_cluster "$c"; continue
        fi
        if ! pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" docker ps >/dev/null 2>&1; then
            echo "x 'docker ps' failed, so nothing can be asked of container $c - and 'no" >&2
            echo "  access' is not the same fact as 'nothing to do'. Nothing was written." >&2
            echo "  fix: grant docker access, then run $SETUP_CMD. Immediate alternative:" >&2
            echo "  export ODOO_PG_PASSWORD=... for this shell." >&2
            _bad_cluster "$c"; continue
        fi
        rc=0
        pg_publish_is_loopback_only "$c" || rc=$?
        if [[ "$rc" -eq 1 ]]; then
            echo "x $c publishes its port on a NON-loopback address (named above)." >&2
            echo "  Trusting this host's gateway would then trust anyone who can reach that" >&2
            echo "  address, so nothing was written. fix: re-publish the port on 127.0.0.1" >&2
            echo "  and re-run $SETUP_CMD, or export ODOO_PG_PASSWORD=... and leave the" >&2
            echo "  cluster's rules alone." >&2
            _bad_cluster "$c"; continue
        elif [[ "$rc" -ne 0 ]]; then
            echo "x $c: where its port is published could not be determined, so whether a" >&2
            echo "  trust rule would be safe is unknown - and unknown is never read as safe." >&2
            echo "  Nothing was written. fix: run $SETUP_CMD once docker can answer." >&2
            _bad_cluster "$c"; continue
        fi
        # Which role may ask this cluster about itself - asked, not assumed. Every
        # question from here down (SHOW hba_file, pg_hba_file_rules, pg_reload_conf)
        # is superuser-restricted.
        su="$(_cluster_superuser "$c" "${ulist[0]}")"
        if [[ "${_SU_PROVEN:-0}" -eq 1 ]]; then
            echo "  asking this cluster about itself as its superuser role '$su'"
        else
            echo "  note: no superuser role could be CONFIRMED on $c, so the cluster's own"
            echo "        questions are asked as '$su'. The ones that are superuser-only will"
            echo "        report 'not permitted' rather than being read as absent."
        fi
        hba="$(pg_hba_file_path docker "$c" "" "$su" "")" || hba=""
        if [[ -z "$hba" ]]; then
            echo "x $c: the server did not report its hba_file, so the file to edit is" >&2
            echo "  unknown - and editing a guessed path changes nothing while looking like" >&2
            echo "  success. Nothing was written." >&2
            if pg_err_denied; then
                # The cluster ANSWERED - it answered "you may not ask". Naming
                # "start the cluster" here would send the reader to restart
                # something that is already running, and `check` would keep
                # returning 1 forever.
                echo "  cause: 'SHOW hba_file' is superuser-only (GUC_SUPERUSER_ONLY) and role" >&2
                echo "  '$su' is not a superuser - the cluster is RUNNING and refused the" >&2
                echo "  question, it is not down. fix: let this step reach a superuser role" >&2
                echo "  (the stock image trusts its POSTGRES_USER over the container socket)," >&2
                echo "  or export ODOO_PG_PASSWORD=... and leave this cluster's rules alone." >&2
            else
                echo "  fix: start the cluster, then run $SETUP_CMD. If it IS running, the" >&2
                echo "  question was refused rather than unanswered - see the server's own" >&2
                echo "  message above." >&2
            fi
            _bad_cluster "$c"; continue
        fi
        if ! pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" docker exec "$c" \
                sh -c 'test -w "$1" && test -w "$(dirname "$1")"' _ "$hba" >/dev/null 2>&1; then
            echo "x $c: the exec identity cannot write $hba or its directory, so the edit" >&2
            echo "  and its atomic rename would both fail. Nothing was written - no backup" >&2
            echo "  was taken either. fix: run $SETUP_CMD once the container can be written" >&2
            echo "  to, or export ODOO_PG_PASSWORD=... for this shell." >&2
            _bad_cluster "$c"; continue
        fi
        baseline="$(_psql_scalar docker "$c" "" "$su" "" \
            "SELECT count(*) FROM pg_hba_file_rules WHERE error IS NOT NULL")" || baseline=""

        _APPLY_ADDRS=""
        if ! _apply_one_cluster "$c" "$hba" "$su" "${ulist[@]}"; then
            _bad_cluster "$c"; continue
        fi
        for u in "${ulist[@]}"; do
            _verify_cluster_rungs "$c" "$su" "$u" "$_APPLY_ADDRS" "$baseline" || failed=1
        done
        _pgdata_mount_report "$c" "$hba"
        echo "  revert with: $(basename "$0") revert"
    done <<<"$containers"

    # PASS 3 - rung 3, per INSTANCE, because each declares its own interpreter and
    # its own connection. This is the only rung that can permit exit 0: the two
    # above read the server's opinion of its own config, and neither reproduces
    # the connection a build makes.
    local i=0 proven=0 unproven=0 inst_container=""
    while [[ "$i" -lt "${#sel_series[@]}" ]]; do
        series="${sel_series[$i]}"; profile="${sel_profile[$i]}"
        inst_container="${sel_container[$i]}"; i=$((i + 1))
        label="$(_label "$series" "$profile")"
        _load_instance "$series" "$profile" || continue
        # Keyed off PASS 1's routing decision, not off db_run_mode: a native-client
        # instance whose SERVER is a container was edited above, so its reconnect
        # must be run here too - reading db_run_mode again would skip it and the
        # step would report "nothing was proven" after a successful edit.
        [[ -n "$inst_container" ]] || continue
        # A cluster that was refused above was never touched, so there is nothing
        # here for a reconnect to prove either way.
        case "
$bad_clusters" in *"
${inst_container}
"*) continue ;; esac
        rc=0
        _preflight_from_host "${INST_PYTHON:-}" "${INST_DB_HOST:-localhost}" \
            "${INST_DB_USER:-odoo}" "${INST_DB_PORT:-}" "${INST_ODOO_ROOT:-}" || rc=$?
        case "$rc" in
            0) echo "  rung 3 ok: $label - Odoo authenticated from the host, no password"
               proven=$((proven + 1)) ;;
            # 20 means the QUESTION could not be asked: this instance declares no
            # runnable interpreter, which a `run_mode = "docker"` instance does BY
            # DESIGN (compose launches Odoo, so no python of its own is recorded).
            # `check` already treats 20 as undeterminable; counting it as unproven
            # here made the step report FAILURE - and advise reverting the block
            # that had just made a sibling instance on the same cluster work.
            20) echo "  rung 3 UNDETERMINED for $label: no runnable 'python' is declared, so"
                echo "         Odoo's own connection cannot be reproduced from here. Neither a"
                echo "         yes nor a no; nothing is claimed for this instance."
                echo "         fix (optional): 45-venv.sh record-env --series $series" ;;
            *) echo "x rung 3 FAILED for $label (exit $rc): the reconnect above did not report" >&2
               echo "  DB_AUTH=ok, so this step's success is NOT claimed - the verdict and its" >&2
               echo "  remedy are the ones the reconnect printed. Undo with" >&2
               echo "  '$(basename "$0") revert', or restore the backup path printed above." >&2
               unproven=$((unproven + 1)) ;;
        esac
    done

    if [[ "$failed" -ne 0 || "$unproven" -ne 0 ]]; then
        return 1
    fi
    [[ "$proven" -gt 0 ]] && return 0
    echo "x nothing was proven: no declared instance reached the reconnect check." >&2
    return 1
}

# ---------------------------------------------------------------------------
# revert - remove the managed block and reload. The named backup stays where it
# is: it is the second escape route, and this step never deletes one.
# ---------------------------------------------------------------------------
cmd_revert() {
    local want_series="" want_profile=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --series) want_series="$2"; shift 2 ;;
            --profile) want_profile="$2"; shift 2 ;;
            *) echo "Unknown argument: $1" >&2; return 2 ;;
        esac
    done
    [[ -f "$INSTANCES_TOML" && -f "$HBA_EDIT" ]] || return 1
    local series profile label c hba failed=0 su=""
    local seen=""
    while IFS=$'\t' read -r series profile; do
        [[ -n "$series" ]] || continue
        [[ -z "$want_series" || "$series" == "$want_series" ]] || continue
        [[ -z "$want_profile" || "$profile" == "$want_profile" ]] || continue
        _load_instance "$series" "$profile" || continue
        label="$(_label "$series" "$profile")"
        # The SAME routing `apply` used (see _container_publishing): a native-client
        # host whose SERVER is a container was edited by `apply`, so `revert` must be
        # able to undo it. Keying this on db_run_mode alone would leave exactly those
        # hosts with a managed block and no way back through this step.
        c=""
        case "${INST_DB_RUN_MODE:-}" in
            docker) c="${INST_DB_CONTAINER:-}" ;;
            native) c="$(_container_publishing "${INST_DB_PORT:-}" 2>/dev/null)" || c="" ;;
        esac
        [[ -n "$c" ]] || continue
        case "
$seen" in *"
$c
"*) continue ;; esac
        seen="$seen$c
"
        su="$(_cluster_superuser "$c" "${INST_DB_USER:-odoo}")"
        hba="$(pg_hba_file_path docker "$c" "" "$su" "")" || {
            echo "x $label: $c did not report its hba_file - nothing was reverted." >&2
            if pg_err_denied; then
                echo "  cause: 'SHOW hba_file' is superuser-only and role '$su' is not one -" >&2
                echo "  the cluster is running and refused the question." >&2
            fi
            failed=1; continue
        }
        local tmpdir cur new
        tmpdir="$(mktemp -d)"; cur="$tmpdir/cur"; new="$tmpdir/new"
        if ! pg_bounded_run "$PG_MODE_PROBE_TIMEOUT" \
                docker exec "$c" cat "$hba" >"$cur" 2>/dev/null; then
            echo "x $c: could not read $hba - nothing was reverted." >&2
            rm -rf "$tmpdir"; failed=1; continue
        fi
        if ! python3 "$HBA_EDIT" revert --file "$cur" >"$new"; then
            echo "x $c: the file could not be rewritten (see above) - nothing was reverted." >&2
            rm -rf "$tmpdir"; failed=1; continue
        fi
        if cmp -s "$cur" "$new"; then
            echo "  $c: no managed block present - nothing to revert"
            rm -rf "$tmpdir"; continue
        fi
        # Back up here too: a human may have added a line INSIDE the markers, and
        # removing the block removes that with it. Cheap, and it makes this
        # direction as recoverable as the other.
        local rbak=""
        if rbak="$(_hba_backup_path docker "$c" "$hba")" && pg_bounded_run \
                "$PG_MODE_PROBE_TIMEOUT" docker exec "$c" cp -p "$hba" "$rbak" \
                >/dev/null 2>&1; then
            echo "  backup -> $c:$rbak"
        else
            echo "x $c: could not back up $hba - nothing was reverted." >&2
            rm -rf "$tmpdir"; failed=1; continue
        fi
        if ! _write_hba_atomically "$c" "$hba" "$new"; then
            # Same rule as `apply`: ASK the file, never assert its state.
            _report_write_outcome "$c" "$hba" "$cur" "$new" "$rbak" || true
            rm -rf "$tmpdir"; failed=1; continue
        fi
        rm -rf "$tmpdir"
        echo "  removed the managed block from $c:$hba"
        _psql_scalar docker "$c" "" "$su" "" \
            "SELECT pg_reload_conf()" >/dev/null || {
            echo "x $c: reload could not be asked for; the OLD rules are still live." >&2
            if pg_err_denied; then
                echo "  cause: pg_reload_conf() is superuser-only and role '$su' is not one." >&2
            fi
            failed=1; continue
        }
        echo "  reloaded $c - the cluster's own rules decide again"
    done < <(_enumerate_instance_keys "$INSTANCES_TOML")
    [[ "$failed" -eq 0 ]] || return 1
    return 0
}

# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------
# Open the "why did that question fail" channel for the whole run (see
# pg_mode.sh's pg_err_* block) and remove it however this script exits. Opened
# HERE, in the top-level shell, because every consumer reads it after a command
# substitution has already returned - a channel opened inside one would die with
# the subshell that opened it.
pg_err_open
trap 'pg_err_close' EXIT

case "${1:-}" in
    describe) cmd_describe ;;
    check)    shift || true; cmd_check "$@" ;;
    apply)    shift; cmd_apply "$@" ;;
    revert)   shift; cmd_revert "$@" ;;
    *) echo "Usage: $(basename "$0") {describe|check|apply|revert} [--series X.Y] [--profile P]" >&2
       exit 2 ;;
esac
