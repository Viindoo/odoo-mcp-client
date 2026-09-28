# WORKTREE_PATH substitution (the addons list a worktree build leases)

Run this before `lease_acquire` whenever the build must load a worktree's code. `WORKTREE_PATH`
absent or `none` -> skip it; the catalog list is used as-is. Never edit the catalog.

1. `WT=$(cd <WORKTREE_PATH> && pwd -P)` and
   `PRINCIPAL=$(git -C "$WT" rev-parse --path-format=absolute --git-common-dir)`; strip a trailing
   `/.git` from `$PRINCIPAL` to get the principal checkout root.
2. Start from the `addons_path` list of the catalog row serving this series (`catalog_read`, or
   `catalog_locate` with `$WT`), in its order.
3. DROP every entry whose `pwd -P` equals `$PRINCIPAL` or lies under `$PRINCIPAL/`.
4. PREPEND one replacement per dropped entry, same relative suffix under `$WT`, same order
   (a dropped `$PRINCIPAL/addons` becomes `$WT/addons`; a dropped bare `$PRINCIPAL` becomes `$WT`).
5. Steps 3-4 dropped ZERO entries -> return
   `BLOCKED(no catalog addons entry lies under <PRINCIPAL> - this worktree's modules were never on
   this instance's addons-path; declare the repo's addons dir via /odoo-setup)`. Do NOT proceed: a
   suite run on an addons path that cannot contain the edited module proves nothing.
6. Pass the result as `lease_acquire`'s `addons_path`, with `cwd` = `$WT`. Core, enterprise, theme
   and every other non-repo entry is carried through untouched.

The lease acquired with this list is yours: clear it before your terminal status - `lease_release`
with its `lease_token` and your `run_id`, `lease_park`, or forward the handle to a named catcher
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1).
