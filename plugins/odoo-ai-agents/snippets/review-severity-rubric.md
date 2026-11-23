# Review Severity Rubric

Every finding - reviewer or audit - reports on this one scale, folds in by this one rule, and is
owned by exactly one producer per pass.

## 1. The scale

**CRITICAL / HIGH / MED / LOW**. The three dedicated audits map their native tiers into it (§ 2).

A CRITICAL or HIGH finding on behaviour states its scenario: the state or input, and the wrong
result a role or a caller observes. A mechanical finding (a rule and the line that breaks it)
needs none. `NEEDS_JUDGEMENT: <question>` is an open question for the next pass or the human,
never a severity: a mechanical check no tool result answers, or a behaviour concern for which no
scenario can be stated.

## 2. Audit-tier mapping

Map by IMPACT, never by an Odoo version: the same tier carries the same severity on every series.

- **`odoo-deprecation-audit`**: `BREAKING` -> CRITICAL when the symbol is already removed at the
  pinned version, HIGH when deprecated with removal scheduled but still present; `WARN` -> MED;
  `STYLE` -> LOW.
- **`odoo-security-audit`**: by exploit path - an unauthenticated injection or RCE path is
  CRITICAL; a privilege-widening `sudo()` is HIGH; a missing `groups=` on a low-sensitivity field
  is MED; a hardening nit is LOW.
- **`odoo-perf-audit`**: by impact - an unbounded query on the hot path of a high-volume model is
  CRITICAL or HIGH; an N+1 in a low-volume loop is MED; a missing `index=True` with no observed
  load is LOW.

## 3. Fold-in rule (diff vs pre-existing)

- A finding **inside the diff** at CRITICAL or HIGH forces the verdict to `REQUEST_CHANGES`; MED
  and LOW inside the diff are advisory. The fix of a finding inside the diff belongs to the
  commit that introduced it, never to a follow-up commit
  (`${CLAUDE_PLUGIN_ROOT}/snippets/commit-history.md`).
- A finding **outside the diff** (pre-existing, blast radius) never changes the diff verdict or
  score, at any severity. It surfaces as a `concerns:` note carrying an opt-in `next:` (e.g.
  `next: odoo-deprecation-audit` for a full sweep) - never silently dropped, never silently
  blocking the diff. A pre-existing defect the run PROVED in a module the PR touches is expected
  fixed in the PR, in that module's own commit; left unfixed, it is a HIGH concern naming the
  commit it belongs in.

## 4. Ownership-transfer

A dimension handed to its audit in a pass - security, performance or deprecation - is owned by
that audit: the reviewer keeps only the trigger and writes no finding of its own for it. Two
entries on the same file, line and symbol collapse to the audit's entry.
