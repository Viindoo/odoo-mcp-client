# Forward-port: a module that is not installable at the target

A module that is absent from the target clean tip, or carries `'installable': False` there, lands
dormant: `installable: False`, its code a copy of the source, on the lint-only lane below.
Adapting its logic belongs to its upgrade (`odoo-modules-upgrade`), never to the port.

## Discriminator

The state that decides is the TARGET CLEAN TIP - the target branch before the merge - never the
merged tree, where the source side's `installable: True` hides it. P0 records each touched
module's descriptor flags at both refs in `range.md` (`<tgt-descriptor>` per `odoo-forward-port`
Hard rule 11); P2 writes `installable_false: yes | no` on the module's own `merge-log.md` row,
the one field every later phase reads.

| Target clean tip | `installable_false` |
|---|---|
| descriptor absent: the module is new on the target | yes |
| `'installable': False` | yes |
| `installable` true, or the key absent | no - the normal lane |

Unclear whether the source enabled the module only recently, and the range does not touch its
descriptor: P2 launches the read-only `odoo-installable-prober` on the source history and logs
its verdict line.

## Manifest flags

Right after the merge and before any other work on the module, in the descriptor the target
clean tip carries (a new module: the one the merge brought) - never a second descriptor under the
other filename, which Odoo would load in place of the real one:

1. `'installable': False`.
2. `'auto_install': True` and `'application': True`, where present, commented out with
   `# TODO: Uncomment when upgrading module to production-ready status`: the marker
   `odoo-modules-upgrade` reads when it re-opens the three flags together.

`version` and migration directories follow C1 and C2 of `[[fp-merge-absorption]]`, not this file.

## Lint-only lane

What each phase does for a module with `installable_false: yes`:

| Phase | The module |
|---|---|
| P1 intent, P3 design, the EXTRACT and ADAPT tiers | skipped; `plan.md` records its tier as `lint-only` |
| P5 merge | a conflict in its files resolves to the source side, by git-ops; the manifest flags then apply |
| P6 symbol-survival, P6 test-survival, P7 drift scan | no symbol grounding and no scan. The P6 git-ops dispatch proves instead: no conflict marker in its files, the end-state `installable` flag of its descriptor, and its tree equal to the source tip's except the flag lines above |
| P8 adapt | 8c: the manifest flags. A coder runs only for a file that does not parse or a lint failure the gate reports in the module, under the `LINT-ONLY` constraint: fix syntax and lint, adapt no logic, refactor nothing |
| P9 verify | outside the install and test set, so its absence from `modules_installed` is expected. A batch with no installable module has no install set: its verify is the lint gate - `GATE_ROLE: pre-pr-lint-gate` with the modules of `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md` - and a red whose evidence names only files outside the worktree is recorded as pre-existing |
| P9.5 i18n | escape E4 of `${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md` |
| P11 acceptance | outside the acceptance scope. A batch with no installable module records `acceptance: n/a (installable:False at target - lint-only lane)` on the merge log |
| P12 review | syntax and lint findings only |

## Deferring a new module

A new module that cannot be carried in this PR is decided explicitly and recorded on the merge
log: `CARRY installable:False` (the default: it lands dormant on the lane above) or
`DISCARD - <reason>` (the merge is dropped and the source presents the module again next cycle),
chosen when carrying it would break the build beyond a lint fix.
