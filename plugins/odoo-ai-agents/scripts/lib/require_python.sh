#!/usr/bin/env bash
# require_python.sh - SSOT preflight: prove this host has a python3 the setup steps can
# actually USE, and say so plainly when it does not.
#
# THE DEFECT THIS EXISTS FOR. Every setup step that needs to read the instance catalog shells
# out to `python3` and suppresses its stderr, e.g.
#
#     python3 - "$toml" "$LIB_DIR" <<'PY' 2>/dev/null || true
#
# The suppression is correct for its own purpose - an absent optional fact must not spam the
# console - but it makes a BROKEN interpreter indistinguishable from AN EMPTY RESULT. Measured
# consequence: on a host where `python3` did not resolve, `48-db-local-auth.sh apply` enumerated
# zero instances from a catalog that declared one, skipped every pass in silence, and reported
#
#     x nothing was proven: no declared instance reached the reconnect check.
#
# which blames the catalog and names nothing the operator can act on. The interpreter was never
# mentioned. That shape is not specific to one step: `2>/dev/null || true` appears 42 times
# across `scripts/setup-steps/`, and before this file NOTHING anywhere checked that `python3`
# exists (`grep -rn 'command -v python3' scripts/setup-steps/` returned nothing).
#
# HOSTS THIS ACTUALLY HAPPENS ON - none of them exotic:
#   - a version manager (pyenv, asdf, mise, rbenv) whose `python3` is a SHIM that resolves to
#     nothing under the PATH the step runs with;
#   - a container-only or minimal host that ships no system python at all;
#   - a host whose python3 predates `tomllib` (3.11), so `instances_io` imports and then fails.
# The plugin supports hosts with and without Docker, and with and without a system python; a
# preflight is how "without" becomes a diagnosable answer instead of a silent no-op.
#
# CONTRACT
#   PY3                     - the interpreter every caller should invoke, set by this file.
#                             `$ODOO_AI_PYTHON3` wins when set, so an operator can name an
#                             interpreter without touching PATH.
#   require_python3 [label] [module ...]
#                           - 0 when PY3 runs AND can import every named module; otherwise
#                             prints a precise, actionable refusal on stderr and returns 1.
#                             Modules default to `tomllib` (3.11+), which is what reading
#                             instances.toml needs. A caller that only parses JSON should say
#                             so (`require_python3 "<label>" json`) rather than inherit a
#                             stricter floor than its own work requires - refusing a host the
#                             step would have served is the same defect in the other direction.
#
# It is a PREFLIGHT, not a wrapper: it runs once per invocation and leaves the existing
# `2>/dev/null` call sites alone, because once the interpreter is known good their silence
# means what it was always meant to mean - no data, rather than no interpreter.

PY3="${ODOO_AI_PYTHON3:-python3}"

require_python3() {
    local label="${1:-this step}"; shift || true
    local out rc=0 resolved="" mods="" m
    for m in "${@:-tomllib}"; do mods="${mods:+$mods, }$m"; done
    out="$("$PY3" -c "import sys, $mods; sys.stdout.write(sys.executable)" 2>&1)" || rc=$?
    if [[ "$rc" -eq 0 && -n "$out" ]]; then
        return 0
    fi

    resolved="$(command -v "$PY3" 2>/dev/null || true)"
    echo "x $label needs a working python3 and this host does not provide one." >&2
    if [[ -z "$resolved" ]]; then
        echo "  '$PY3' is not on PATH at all." >&2
    else
        echo "  '$PY3' resolves to $resolved but running it failed (exit $rc):" >&2
        printf '    %s\n' "${out:-<no output>}" >&2
    fi
    echo "  This is reported HERE, at the interpreter, because every step downstream reads the" >&2
    echo "  instance catalog through python and would otherwise report an empty catalog instead" >&2
    echo "  of a missing interpreter." >&2
    echo "  Choose ONE:" >&2
    echo "    - install a python3 providing: $mods" >&2
    echo "      (tomllib means 3.11 or newer - it is how instances.toml is read); or" >&2
    echo "    - if one IS installed but not on PATH - a pyenv/asdf/mise shim that resolves to" >&2
    echo "      nothing here is the common case - export ODOO_AI_PYTHON3=/full/path/to/python3" >&2
    echo "      and re-run this step." >&2
    return 1
}
