<!-- SSOT snippet. odoo-bin memory/time resource-limit POLICY (Problem 1 hardening).
     The numeric resolution logic lives ONLY in
     scripts/lib/resource_limits.sh - this file documents the policy those
     values implement; it does not restate full command lines. Consumers
     (55-instance-ops.sh, 50-instance-spinup.sh, and any runnable odoo-bin
     doc literal) point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md. Edit here only. -->

# odoo-bin resource limits

## The one canonical default

`ODOO_AI_LIMIT_MEMORY_HARD` (bytes) resolves to `floor(MemTotal_bytes * 0.5)`, floored at
`4294967296` (4 GiB), when unset. Set it explicitly to override; set it to `""` or `"0"` to opt into
the UNCAPPED escape hatch (defers to Odoo's own default/no cap - see below). Resolution logic lives
ONLY in `scripts/lib/resource_limits.sh` (`resource_limit_hard_bytes` / `resource_limit_hard_kib` /
`resource_limit_is_uncapped`) - never re-derive this formula elsewhere.

## Why re-pinning Odoo's stock default fixes nothing

Odoo's own `--limit-memory-hard` default is 2.5 GiB (`2684354560`) on every version. Passing that
same number back is a no-op. The problem is that 2.5 GiB is too tight for a large install/update, and
the fix is a GENEROUS, OVERRIDABLE cap - not re-declaring the stock number.

## The v12.0 enforcement boundary

Odoo's `set_limit_memory_hard()` (the code that actually calls `setrlimit(RLIMIT_AS, ...)`) is
**absent in v8/v9/v10/v11** and defined + called only from v12 onward, on the `ThreadedServer.start()`
path, BEFORE `preload_registries()`. Consequence: flag SPELLING never varies (`--limit-memory-hard` is
a stable `server` option v8-v19), but ENFORCEMENT does:

- **v8-v11**: Odoo applies no memory cap at all on this path. `--limit-memory-hard` is a no-op here
  (nothing reads it on the build path pre-v12). A shell `ulimit -Sv <kib>` wrapper is the ONLY
  protection - do not omit it, or an oversized install can be kernel-OOM-killed instead of failing
  clean.
- **v12-v19**: Odoo applies its own `setrlimit` using `config['limit_memory_hard']` - which CLAMPS the
  process back down to that value even if a shell `ulimit` already set a higher limit. The
  `--limit-memory-hard=<value>` flag is required here to raise Odoo's own clamp; a bare `ulimit` alone
  would be overridden.

**The version-general rule**: apply BOTH mechanisms unconditionally, driven by the SAME resolved
value - `ulimit -Sv "$(resource_limit_hard_kib)"` immediately before the odoo-bin invocation, PLUS
`--limit-memory-hard=$(resource_limit_hard_bytes)` on the command line. Each is a no-op where the
other version's code path already handles it, and load-bearing where it doesn't. No prose
version-branching is needed - `cli_help` grounding (already required by
`agents/odoo-instance-ops.md`) is a defensive confirm only.

## Uncapped escape hatch

When `resource_limit_is_uncapped` is true (resolved hard cap is `0`/empty): SKIP the `ulimit -Sv`
call entirely AND still pass `--limit-memory-hard=0` on the command line. Odoo's `if
limit_memory_hard:` guard is falsy for `0`, so `setrlimit` is never called - the process runs fully
uncapped, deferring to whatever the OS/container already enforces.

## Canonical copy-safe inline form (doc literals - no sourced script available)

A runnable doc/template that cannot `source scripts/lib/resource_limits.sh` (a bare copy-paste
block, not a `55-instance-ops.sh` invocation) MUST use this exact self-contained line immediately
before the odoo-bin invocation - never a bare `ulimit -Sv "${ODOO_AI_LIMIT_MEMORY_HARD:+...}"`
one-off, which cannot express "unset -> default fires; `0`/empty -> skip" through a single `:+`
expansion (that expression silently no-ops on the unset/default path and runs the destructive
`ulimit -Sv 0` on the `0` escape-hatch value):

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
```

This mirrors `resource_limit_is_uncapped`'s own test (`-z` OR `= "0"`) using the unset-only `-`
substitution (never `:-`, which would wrongly conflate an explicit `""` with "unset" and apply the
default cap instead of honoring the uncap escape hatch) so both documented escape-hatch spellings
(`""` and `"0"`) correctly skip the call, the unset/default path correctly applies the 4 GiB floor,
and a positive override correctly applies. Pair it with `--limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}`
on the odoo-bin line as usual.

## Build path vs long-running listener (A2) - which flags fire where

On the `--stop-after-init` build path (init/update/test - `55-instance-ops.sh`), **ONLY the memory
HARD cap can ever fire**. `limit_memory_soft` and `limit_time_real` live in
`ThreadedServer.process_limit()`, which sits AFTER the `if stop: return rc` short-circuit that
`--stop-after-init` always takes - they are structurally unreachable there. `limit_time_cpu` lives
only in the prefork `Worker.check_limits()`, which needs `workers>0` - never true on this path either.
Do not pass soft/time-real/time-cpu on the build path; they would give false confidence (a flag that
LOOKS like protection but is silently never evaluated).

The A2 long-running listener conf (`50-instance-spinup.sh`'s generated `[options]` block) is the
opposite case: `limit_memory_hard`, `limit_memory_soft`, and `limit_time_real` conf keys ALL fire
there (a real listening `ThreadedServer` reaches `process_limit()`). `limit_time_cpu` stays a DEAD key
there too as long as `workers=0` (this plugin's default; prefork/workers>0 is opt-in and undocumented
here) - do NOT add it; add it only in lockstep with a `workers>0` opt-in that actually spawns prefork
workers.

## Override precedence: defaults BEFORE `--extra` / `${arg_extra}`

The resolved `--limit-memory-hard=<value>` flag (and any other resource-limit default) MUST be placed
in the command line BEFORE the caller-supplied `--extra` / `${arg_extra}` slot. Odoo's argument parser
takes the LAST occurrence of a repeated flag, so a caller who explicitly passes a different
`--limit-memory-hard` in `--extra` always wins - this file's default is a floor, never a ceiling the
caller cannot raise or lower.

## `RLIMIT_AS` is virtual, not physical

`ulimit -Sv` / `RLIMIT_AS` caps VIRTUAL address space, not resident/physical memory. A per-process cap
does not prevent the KERNEL from OOM-killing the box under aggregate multi-session RAM pressure (many
capped processes can still sum to more RAM than the machine has) - what it DOES do is convert a
single oversized install from an ugly, untraceable kernel-OOM-kill into a clean, in-process
`MemoryError`, which `55-instance-ops.sh`'s `_INSTALL_FAIL_RE` already classifies as `STATUS=error`.
Set the cap generously enough to avoid false positives; do not treat it as a substitute for
provisioning enough RAM for however many concurrent sessions you actually run.
