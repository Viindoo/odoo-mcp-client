# Acceptance Oracle Contract

An oracle derived from the implementation or from the system's current output always passes;
derived from the REQUIREMENT it catches the gap between what the code does and what the business
needs.

## The five invariants (non-negotiable)

1. **The oracle comes from the requirement, never from the code of the change or its output.**
   Every `expected` value rests on a requirement sentence it names, or on a value computed
   independently by hand. An outcome the requirement does not state is a question for its owner,
   not a scenario. The SRS acceptance criteria (`<SHARE_DIR>/designs/<slug>-<date>-srs.md`, or
   the header of a design written without an SRS) are the oracle.

   **Independent of the change, not of the platform.** An `expected` about behaviour that exists
   without the change - who may open a screen or a menu, what a core control does, which
   transitions core allows - is the platform's own, read from the index or the source of core and
   of the modules the change does not touch. Where the requirement says in so many words that
   the change alters it, the requirement wins; an `expected` that merely assumes otherwise is
   corrected before the run, never executed to a FAIL.
2. **Author != coder != adjudicator (three separate contexts).** The architect authors the oracle
   in the SRS before any code exists; `odoo-qa-planner` authors a scenario only for a criterion
   that lacks a comparable expected value. Neither is the coder (`odoo-coder`) nor the agent that
   rules PASS or FAIL (`odoo-qa-tester`).
3. **Never edit `expected` to match `actual`.** A disagreement is a FAIL: nothing is widened,
   relaxed, deleted or rewritten to make it green. An oracle that is itself wrong is flagged to
   its author; it is IMMUTABLE to the executor.
4. **PASS requires concrete evidence; missing evidence is UNVERIFIED, never PASS.** Every
   required-evidence item is observed and matches. Reasoning without an artifact is not evidence.
5. **Coverage is systematic.** The techniques below cover classes of input, boundaries and the
   negative paths, not only the happy path.

## Verdicts and observations

Four verdicts, ruled only on a scenario of the oracle:

- **PASS** - the observed result matches `expected` and every required-evidence item was captured.
- **FAIL** - the observed result contradicts `expected`, with the evidence of the contradiction.
- **UNVERIFIED** - required evidence was not obtained (a blocked step, an unavailable role or
  instance).
- **EXTERNAL** - the scenario needs a third-party system this environment cannot reach. It is
  not run, counts neither for nor against the roll-up, and is listed with the system it needs.

Anything else the tester notices - a screen that blocks, a label a role cannot read, a symptom
on a screen no scenario names - is an **observation**: recorded with its evidence, never a FAIL and never a bug. Its
origin is decided at triage (`${CLAUDE_PLUGIN_ROOT}/snippets/fix-round.md`).

## Scenario-design techniques (the author applies all that fit)

Given / When / Then with ONE observable `Then`, equivalence classes, boundary values and a
decision table where conditions combine, plus what Odoo adds:

- **Negative path.** Input that breaks data integrity (an impossible state, a broken reference,
  a duplicate, an access breach, a company mismatch) is refused the right way: correct error, no
  crash, no data leak. A policy or legal violation is NOT refused: the action succeeds and the
  audit flag or warning appears. Every rule gets a positive AND a negative scenario
  (`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md` § 0).
- **Role / permission matrix.** Each role x each action the change guards: the permitted role
  succeeds, the unpermitted role is blocked with the correct error. Access the change does not
  guard is the platform's (invariant 1), not a row of the matrix.
- **CRUD matrix.** Per entity Create / Read / Update / Delete, Duplicate and Archive, and each
  operation's constraints (required, unique, ondelete, cascade).
- **State-transition.** Every legal transition passes; the transitions core forbids or integrity
  requires are blocked, each with its way out (back to draft, cancel this record); a transition
  core allows is never narrowed; buttons appear only in the correct state.

A database is never empty (demo data, earlier scenarios): an `expected` list or
count is stated over the records the scenario's fixture creates, plus the property every other
listed record must have.

Each scenario must be capable of FAILING for the right reason, and one that fails because the
screen or record it names does not exist never ran at all
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-sensitivity-contract.md` § Broken measurement is not a red).
Drive the real workflow when realizing a scenario as an executable test:
`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md`.

**An expected result is never a piece of DISPLAY TEXT** - the wording of a label, button, help
sentence, error message or translated term - nor a transient internal row (a record the flow
creates and then removes, a queue entry, a log line). It is the state, the record produced, the
exception TYPE or the permission refused that the scenario's role observes. Naming a label to
say WHERE to click is addressing and stays fine
(`${CLAUDE_PLUGIN_ROOT}/snippets/test-behavior-contract.md` § Never assert TRANSLATED or DISPLAY
text).
