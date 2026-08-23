<!-- SSOT snippet. How a `--test-enable` run's scope is decided: the two-sided rule, the derivation
     default, the full-run exemptions, and the SCOPING-vs-SUPPRESSION test. WHICH modules enter the
     set is a different question, owned by ${CLAUDE_PLUGIN_ROOT}/skills/_shared/regression-scope.md.
     Flag syntax + per-version availability: ${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md. -->

# Test-Scope Contract (`--test-enable` runs a scope, never "everything installed")

`--test-enable` does not run "the modules you named". It runs every test the registry loaded, and
dependency resolution plus `auto_install` fan-out loads far more than `-i`/`-u` names: `-i sale`
builds a registry reaching down to `base`, and untagged every one of those modules runs its suite.
The runtime is then set by the closure, not by the change - and so is the verdict.

**The bug this removes:** `-i sale --test-enable` where `--test-tags /sale` was meant.

## Two sides, one module set (HARD RULE)

Both sides are derived from ONE resolved module set `M`:

- **Install** (what the registry builds): `-i <M>` on a fresh DB, `-u <M>` on an installed one - `M`
  comma-joined, in dependency order.
- **Selection** (whose tests run): `--test-tags <T>`, where `T` = `/<m>` for every `m` in `M`.

```
-u sale,account --test-enable --test-tags /sale,/account --stop-after-init
```

`M` is the change plus its in-repo blast radius; resolving it belongs to `regression-scope.md`, not
here. A too-narrow `M` is a coverage defect no tagging fixes - this contract only guarantees that
whatever `M` was resolved is what actually gets tested.

## Deriving `T` when the caller supplied none

A caller that resolved a blast radius SHOULD pass its tags. Given none, the executor DERIVES `T =
/<m>` per module in `M` rather than running untagged, and reports that it derived them. That is not
inventing a scope: it is exactly what the caller declared by naming `M`, minus the fan-out they
never asked to verify. Untagged is the option that silently substitutes a far larger scope.

Version-gated: confirm the `/module` selector via `cli_help("server", "--test-tags",
odoo_version='<series>')` - never from memory or a hardcoded series range.

## `TEST_TAGS: full` and the exemptions

`full` is the ONE value meaning "run untagged, on purpose" - a positive declaration, so a reader can
tell a deliberate full run from a forgotten tag. `none` / empty / omitted mean NOT SUPPLIED: derive.

Run untagged only under one of these, and NAME which one in the report:

1. **`TEST_TAGS: full` requested** - a release sweep, or a cross-cutting break with no resolved `M`.
2. **No code change under test** - an environment / upgrade / migration smoke run.
3. **The series has no tag filter** - confirmed absent via `cli_help`. State the consequence (the
   core closure is tested too, and the run is slow); never imply a scoped run happened.
4. **Reproducing a CI/Runbot gate that itself runs untagged** - parity is the point, so the scope
   matches that gate, not the blast radius.

## Two widenings that stay inside the rule

- **Framework `post_install` classes.** `--test-tags` only FILTERS, never ADDS, so a `/<m>` run
  skips framework classes not tagged with your module. NAME them beside the module tags
  (`'/sale,base.TestInvisibleField'`); dropping the filter to reach them is not the remedy. Method +
  how to resolve the class names: `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.
- **Lint modules.** `test_lint` / `test_pylint` are selected by tag but run only if INSTALLED, so a
  build that tags them unions them into `-i`/`-u` from the SAME probe - gated on `GATE_ROLE:
  pre-pr-lint-gate`, owned by `${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md` § Lint modules.

Both widen BOTH sides together. Neither is an exception to the two-sided rule.

## Scoping vs suppression

- **SCOPING (correct):** `T` covers every module in `M`. Fan-out outside `M` was never in scope, so
  not running it hides nothing.
- **SUPPRESSION (defect):** `T` covers FEWER modules than `M`, or an unrequested `skip-auto-install`
  stops a module the caller DID declare from being exercised. That manufactures a false green -
  worse than a noisy run.

Deriving `T` from `M` is always allowed. Narrowing below `M` never is - not to quiet a failing
dependency, not to fit a timeout. The ONE carve-out is a RED PROBE
(`${CLAUDE_PLUGIN_ROOT}/snippets/red-evidence-contract.md`): a single-test run whose GREEN licenses
nothing - it signals a defective test. Any run whose green lets work PROCEED is a verdict run and
never narrows. A failure inside `M` is in scope and BLOCKING even in a module the
change did not touch.

## Reporting

In the run's `notes`: the **tags used and their provenance** (caller-supplied / derived / `full`
under a named exemption); **modules actually loaded** and **tests actually run**, read from THIS
run's log (`unknown` when it carries no figure - never estimated); and any failing test whose module
is outside `M`, named as out of scope so a pre-existing failure routes separately. The verdict never
softens: out-of-scope still fails, still blocks.

Those figures expose a scope that did not hold - tags meant to bound the run to two modules beside a
log reporting thousands of tests.
