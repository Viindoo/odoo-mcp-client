<!-- SSOT snippet. The modularity invariant every code, test, review and acceptance step checks
     by machine. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/modularity-contract.md. -->

# Modularity Contract

An Odoo module works on its own, for the purpose its manifest states, using only what it declares.
Every step below is a check with a true-or-false answer; none needs judgement.

## The invariant

A module may reference a model, field, method, xml_id, asset, group or record ONLY when the module
that owns it is the module itself or a member of the module's upstream `depends` closure (the
transitive closure of `depends` in its manifest). A reference to anything else is a CRITICAL
finding: the module cannot install alone, and it works only by accident of what else is installed.

## The check, per reference

1. Resolve the owner of the referenced symbol: a symbol defined in a module of the worktree set
   `W` is owned by that module (read the disk); otherwise `entity_lookup` names the owner
   (`${CLAUDE_PLUGIN_ROOT}/snippets/osm-first-contract.md` § The tree under edit).
2. Build the upstream closure of the referencing module: its manifest `depends` on disk,
   recursively; modules outside `W` through `module_inspect` (`dependencies`).
3. The owner is in the closure -> pass. Not in the closure -> CRITICAL, with the fix named: add
   the owner to `depends` when the dependency is intended, else move the reference to a module
   that already depends on both.

Where it runs: the coder on every new reference it writes (the row goes into `impact-map.md`
with the owner, the closure answer and its source); review `R1` on every new reference in the
diff; the test writer on every record a test creates or reads.

## Tests

- A module's tests create or read data only from the module and its upstream closure. Demo data
  of a module outside the closure is never a fixture.
- The module's tests pass on a database that contains ONLY the module and its upstream closure
  (`odoo-bin -i <module>` on a fresh database). That run is the proof the module stands alone.
- A module with dependents in the repo (a grep of every manifest for `depends` naming it, plus
  `impact_analysis` as a lower bound) also runs its dependents' tests once, on a database with
  those dependents installed. That run is the proof nothing downstream broke.

## Acceptance

The acceptance instance is built from the worktree with ONLY the node's modules and their
upstream closure (`odoo-instance`, install set = closure). When dependents exist in the repo, a
second database adds them; every scenario runs on both, and a FAIL on the first database is
reported as "module does not stand alone", never softened by a PASS on the second.

## Design

An SRS states, per module, the purpose the module serves on its own. A design that makes a
module need a sibling's data without declaring the dependency is rejected at the design gate,
not discovered at review.
