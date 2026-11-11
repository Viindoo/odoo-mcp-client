# odoo-bin resource limits

`instance_build`, `instance_serve` and `instance_i18n_export` apply this policy for you. To change
the cap for one build pass `--limit-memory-hard=<bytes>` in `extra_args` (§ Override precedence).

## The one canonical default

`ODOO_AI_LIMIT_MEMORY_HARD` (bytes), when unset, resolves to half of the machine's memory with a
floor of `4294967296` (4 GiB). Set it to override; set it to `""` or `"0"` for no cap at all. The
resolution lives only in `scripts/lib/resource_limits.sh` (`resource_limit_hard_bytes`,
`resource_limit_hard_kib`, `resource_limit_is_uncapped`): never re-derive it. Odoo's own default
for `--limit-memory-hard` (2.5 GiB) is too tight for a large install, which is why the tools pass
a generous value instead of leaving it.

## What caps a launch

Every `odoo-bin` the plugin starts goes through `scripts/lib/run_bounded.sh`, which applies the
resolved value in the strongest way the host offers:

- **A memory-capped scope of its own**, where a systemd user manager enforces one: the process
  tree runs outside the session's own unit with a resident-memory limit and no swap. A tree that
  exceeds it is killed alone - the session, its other agents and the other servers keep running.
- **Otherwise an address-space limit** on the process (`ulimit -Sv`): it turns an oversized
  allocation into an error inside that process. It is per process and virtual, so it does not stop
  the kernel from choosing a victim when many processes together exhaust the machine.

`--limit-memory-hard=<bytes>` is passed as well, with the same value: see the next section.

## The v12.0 enforcement boundary

The option's spelling is the same on every series; what reads it differs:

- **v8-v11**: Odoo applies no memory cap on this path, so the launcher's cap is the only one.
- **v12 and later**: Odoo sets its own limit from `limit_memory_hard` and clamps the process down
  to it even under a higher shell limit, so the option must carry the resolved value.

Applying both, from the same value, is correct on every series.

## Uncapped

With the cap resolved to `0` or empty the launcher adds no limit and `--limit-memory-hard=0` is
still passed: Odoo skips its own limit for `0`, so the process runs under whatever the host
enforces.

## A heavy command of your own

A command you start yourself that can grow without bound (a batch over many images, a
documentation build, a data crunch) runs under the same cap:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/run_bounded.sh capped <command> [args...]
```

Never wrap a command in a scope by hand: the launcher also protects the arguments from being
rewritten on the way. A command killed for memory ends with status 137 (or, under the fallback,
with its own out-of-memory error): make the work smaller before running it again, never the same
command unchanged.

## Copy-safe inline form (for a command line a human will paste on another host)

A printed command that cannot use the plugin's scripts carries this line right before `odoo-bin`,
with `--limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}` on the `odoo-bin` line:

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
```

Unset applies the default, `""` or `"0"` skips the limit, a positive value applies it. Do not
shorten it to a `:+` expansion: that form skips the default and runs `ulimit -Sv 0` on the `0`
escape value.

## Build path vs long-running listener

On a `--stop-after-init` build (init, update, test) only the memory hard cap can fire: the soft
memory limit and the real-time limit are evaluated in the serving loop a build never reaches, and
the CPU-time limit only in prefork workers. Do not pass those on a build. The generated
configuration of a served instance carries `limit_memory_hard`, `limit_memory_soft` and
`limit_time_real`, which all apply there; `limit_time_cpu` is added only together with prefork
workers.

## Override precedence

The resolved `--limit-memory-hard=<value>` is placed before the caller's `extra_args`: Odoo keeps
the last occurrence of a repeated option, so a caller's own value wins in either direction.
