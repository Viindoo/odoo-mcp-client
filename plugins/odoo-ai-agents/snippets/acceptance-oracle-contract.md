<!-- SSOT snippet. The anti-bias contract for acceptance: how an oracle is DERIVED, who
     owns each role, and what counts as a verdict. Referenced (not copy-pasted) by
     odoo-qa-planner, odoo-qa-tester, odoo-acceptance, odoo-test-writing, and odoo-qa-suite.
     Orthogonal to test-behavior-contract.md (that one governs HOW a written test is arranged
     to exercise behavior; this one governs WHERE the expected result comes from and who may
     decide PASS). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-oracle-contract.md. -->

# Acceptance Oracle Contract (derive the truth from intent, never from the code)

An acceptance oracle is the source of truth that decides whether an observed result is CORRECT
for a given input. An oracle derived from the implementation - or from the output the system
is currently producing - passes at all times, catches zero bugs, and rationalizes whatever the
code happens to do. An oracle derived from the REQUIREMENT catches the gap between what the code
does and what the business needs. That gap is the bug. These rules make the oracle independent.

## The five invariants (non-negotiable)

1. **Oracle comes from requirement/intent, not from code or output.** Every `expected` value is
   derived from the stated requirement, the acceptance criteria, the business rule, or a value
   you compute independently by hand (an independent/calculated oracle). NEVER read the
   implementation to decide what `expected` should be, and NEVER set `expected` to whatever the
   running system returned. Reading the implementation to learn what `expected` should be is the
   defect this contract exists to prevent.

   The SRS acceptance criteria (`<SHARE_DIR>/designs/<slug>-<date>-srs.md`, or the header of a
   design written without an SRS) are the oracle: requirement-derived by the architect, never
   code- or OSM-derived. Reading them is reading the requirement, not the code.
2. **Author != coder != adjudicator (three separate contexts).** The oracle is authored by the
   architect in the SRS, before any code exists; `odoo-qa-planner` authors a scenario only when an
   SRS criterion lacks a comparable expected value. Neither is the coder that wrote the code
   (`odoo-coder`), and neither is the agent that compares system-vs-oracle and rules PASS/FAIL
   (`odoo-qa-tester`). Independence is structural - each runs in its own context.
3. **Never edit `expected` to match `actual`.** When the system disagrees with the oracle, the
   verdict is FAIL - you do NOT widen, relax, delete, or rewrite the expected value to make it
   green. If the oracle itself is genuinely wrong (the requirement was misread), flag it back to
   the planner (See-Something-Say-Something); never silently amend it. The oracle file is IMMUTABLE
   to the executor.
4. **PASS requires concrete evidence; missing evidence = UNVERIFIED, never PASS.** A scenario is
   PASS only when each of its required-evidence items is actually observed and matches the oracle.
   "Looks fine", "seems to work", or reasoning without an artifact is NOT evidence. A step that
   could not be observed (no instance, blocked, browser error) is UNVERIFIED - the default for the
   absence of proof is UNVERIFIED, never PASS.
5. **Coverage is systematic, not whatever was easy to think of.** Apply the scenario-design
   techniques below so the oracle covers classes of input, boundaries, and the negative/forbidden
   paths - not only the happy path the author first imagined.

## Verdict vocabulary (the only three; shared by planner, tester, adjudicator)

- **PASS** - the observed result matches the oracle's `expected` AND every required-evidence item
  for the scenario was captured.
- **FAIL** - an observed result contradicts the oracle's `expected` (the system did the wrong
  thing, crashed, leaked data, or allowed a forbidden action). Always accompanied by the evidence
  that proves the contradiction.
- **UNVERIFIED** - required evidence was not obtained (step blocked, instance/role unavailable,
  evidence not captured). Not a PASS and not a FAIL - it is unproven. Surface it; do not bury it.

## Scenario-design techniques (the author applies all that fit)

- **Given/When/Then (GWT).** Each scenario: `Given <precondition/state> When <action> Then
  <observable result>`. The `Then` IS the oracle - one observable outcome (return value, state
  change, side-effect record, rendered UI, raised error), chosen before execution.
- **Equivalence partitioning (EP).** Split each input into classes (valid and invalid); test one
  representative per class. Wide coverage with few scenarios.
- **Boundary value analysis (BVA).** After EP, probe the edges: min-1 / min / min+1 ... max-1 /
  max / max+1 - where off-by-one bugs live.
- **Negative path.** Malformed/illegal input and forbidden actions MUST be refused the right way:
  correct error, no crash, no data leak. Every rule gets a positive AND a negative scenario.
- **Role / permission matrix.** Each role x each guarded action: the permitted role succeeds; the
  unpermitted role is blocked with the correct error (the spine of RBAC acceptance).
- **CRUD matrix.** Per entity cover Create / Read / Update / Delete (plus Duplicate and Archive in
  Odoo) and each operation's constraints (required, unique, ondelete, cascade).
- **State-transition.** For a state machine (statusbar), exercise every legal transition AND assert
  illegal transitions are blocked; buttons appear only in the correct state.
- **Decision table.** When several conditions combine into several outcomes, tabulate so no
  combination is missed.

Each scenario must be capable of FAILING for the right reason - a scenario that cannot fail
protects nothing - and one that fails because the screen or record it names does not exist never
ran at all (`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Broken measurement is
not a red). Drive the real workflow when realizing a scenario as an executable test:
`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` (reference, do not duplicate).

**An expected result is never a piece of DISPLAY TEXT.** Write it as the state, the record produced,
the exception TYPE, or the permission refused - never as the wording of a label, button, help
sentence, error message, or translated term. That wording is improved independently of the behavior,
so an oracle pinned to it reports FAIL on an improvement: a false verdict, the most expensive kind.
Naming a visible label to say WHERE to click is addressing and stays fine; making it the expected
RESULT is not. Nor is the expected a transient internal row (a record the flow creates and then
removes, a queue entry, a log line): it is the outcome the scenario's role observes. Rule + substitutions:
`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` § Never assert TRANSLATED or DISPLAY
text.
