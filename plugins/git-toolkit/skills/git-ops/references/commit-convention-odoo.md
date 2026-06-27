# Commit Convention - ODOO standard

Loaded by `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` when detection resolves to ODOO
(history shows `[TAG] module:` subjects, or the repo has `__manifest__.py` files). The universal
business-subject rule and the 50/72 limits in that snippet ALWAYS apply on top of this. Source:
odoo.com git guidelines (consistent across v16-v19).

## Subject format (mandatory)

```
[TAG] module: short description
```

- Square-bracket TAG, no space inside the brackets.
- `module` = technical name (`sale`, `account`, `viin_fleet`), NOT a functional label.
- Colon + single space after the module.
- Description forms a valid sentence completing "if applied, this commit will <description>".
  Sentence case; no trailing period; subject <= 50 ideal, 72 hard ceiling.
- Multiple modules: `[TAG] sale, account: ...` or `[TAG] various: ...`. No module (infra/repo-wide):
  omit it - `[TAG] description`.

## TAG decision table

| TAG | Use when |
|---|---|
| `[FIX]` | bug fix (stable or dev branch) |
| `[IMP]` | incremental improvement / feature work in dev (most common when no other tag fits) |
| `[ADD]` | adding a new module |
| `[REM]` | removing code/views/modules (dead-code removal) |
| `[REF]` | refactor - heavy rewrite, behavior unchanged |
| `[MOV]` | moving files (`git mv`) or code between files, NO content change |
| `[REV]` | reverting a prior commit |
| `[MERGE]` | merge commits; also forward-port of fixes |
| `[CLA]` | Contributor License Agreement signing |
| `[I18N]` | translation files (.po/.pot) |
| `[REL]` | release commits |
| `[PERF]` | performance patches |
| `[CLN]` | code cleanup |
| `[LINT]` | linting/formatting only |

Decision order: revert -> `[REV]`; move only -> `[MOV]`; translation -> `[I18N]`; new module ->
`[ADD]`; removal -> `[REM]`; release -> `[REL]`; merge/fwd-port -> `[MERGE]`; cleanup ->
`[CLN]`/`[LINT]`; perf -> `[PERF]`; bug fix -> `[FIX]`; behavior-preserving rewrite -> `[REF]`;
everything else (feature/incremental) -> `[IMP]`.

## Body: WHY, not HOW (mandatory)

Odoo rule, verbatim: "Spend a lot more time describing WHY the change is being done rather than WHAT
is being changed. The diff shows the what. The why is crucial for future understanding." Body
conveys the business problem, purpose, rationale, design decision - NOT method names or loop logic.
A technical choice may be explained only to justify WHY that path was chosen.

## References (end of body, after a blank line)

```
task-1234567       internal task number
opw-123456         OPW support ticket
Fixes #N           closes GitHub issue N
closes odoo/odoo#N closes issue in another repo
```

## Example (GOOD)

```
[FIX] sale: prevent confirm on expired pricelist

Users could confirm sales orders referencing a pricelist past its
end_date, silently applying stale prices - revenue leakage found in a
post-period audit.

task-2045123
Fixes #12345
```

## Example (BAD)

```
[IMP] sale: add check in _action_confirm

Added a check in _action_confirm() iterating over order_line ids and
calling pricelist._check_validity() for each before confirming.
```

Bad: the body describes HOW (method, iteration) not WHY (the business harm prevented).

## Viindoo note

Viindoo follows standard Odoo conventions; module names use Odoo technical naming (`viin_account`,
`viin_fleet`). `[MERGE]` is the canonical forward-port tag (not `[FW]`). Manifest `version` is the
SHORT `x.y.z` form, no series prefix.
