# WORKTREE_PATH substitution (the addons list a worktree build leases)

Run this before `lease_acquire` whenever the build must load a worktree's code. `WORKTREE_PATH`
absent or `none` -> skip it; the catalog list is used as-is. Never edit the catalog.

1. `WT=$(cd <WORKTREE_PATH> && pwd -P)` and `PRINCIPAL` = the `principal_root` of a `repo_facts`
   call on `$WT` (the principal checkout root).
2. Start from the `addons_path` list of the catalog row of the series the build runs
   (`catalog_read` with that series; several rows: the one with an entry under `$PRINCIPAL`), in
   its order.
3. DROP every entry whose `pwd -P` equals `$PRINCIPAL` or lies under `$PRINCIPAL/`.
4. PREPEND one replacement per dropped entry, same relative suffix under `$WT`, same order
   (a dropped `$PRINCIPAL/addons` becomes `$WT/addons`; a dropped bare `$PRINCIPAL` becomes `$WT`).
5. Steps 3-4 dropped ZERO entries -> return
   `BLOCKED(no addons entry of the <series> catalog row lies under <PRINCIPAL>: the worktree
   belongs to a checkout that series does not build from - create it from the checkout the row
   names, or declare this one via /odoo-setup)`. Do NOT proceed: a suite run on an addons path
   that cannot contain the edited module proves nothing.
6. Pass the result as `lease_acquire`'s `addons_path`, with `cwd` = `$WT`. Core, enterprise, theme
   and every other non-repo entry is carried through untouched.

The lease acquired with this list is yours: clear it before your terminal status
(`${CLAUDE_PLUGIN_ROOT}/snippets/resource-teardown-contract.md` T1).
