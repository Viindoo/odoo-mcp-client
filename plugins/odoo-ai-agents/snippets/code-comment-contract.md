<!-- SSOT snippet. Comment + docstring rules for shipped SOURCE; prose ARTIFACTS stay in
     artifact-voice.md. Edit here only; consumers cross-ref, never restate. -->

# Code Comment and Docstring Contract

Governs every comment and docstring you write into source - Python, JS/OWL, XML, SCSS, tests,
migrations. A comment is code you cannot compile: nothing checks it, so it rots by default.

## 1. Default to no comment

Write one only when the WHY is not visible in the code: a hidden constraint, a non-obvious
invariant, a workaround for a specific upstream defect, or behavior that would surprise the next
reader. If deleting it would not confuse that reader, it must not exist - well-named identifiers
already state WHAT the code does. Rename before you annotate: a comment explaining an unclear name
is a naming defect.

## 2. State the purpose, not the mechanics

A comment that earns its place says what the code SERVES: the rule it enforces, the constraint it
respects, the reason that still holds. It never narrates steps the reader can see.

## 3. Banned outright

- **Attribution / self-defense** - "this bug pre-existed", "not introduced by this change", "kept
  for safety", "as requested in review". You address a reviewer, not the next reader; it is noise
  the moment the change merges.
- **Process narration** - "first tried X, then Y", "after investigating", "refactored from".
- **Provenance** - ticket/PR numbers, dates, author or agent names, "used by X", "added for the Y
  flow". Those belong in the commit message.
- **Before/after** - "no longer", "previously", "the new behavior". (An EXTERNAL Odoo version fact
  such as an API removed in a given series is domain knowledge - keep it.)
- **Unshippable references** - anything that does not exist in the repository the code ships in: a
  design doc, survey, worklog, review, QA oracle, plan or evidence file under the run's state dir,
  an absolute or worktree path, a run id, slug, or instance handle. Your brief hands you those as
  inputs; they are YOUR working context, and they will not exist for whoever opens the file next.
  State the reason itself, never where you read it.
- **Commented-out code**, and banner or separator comment blocks.

## 4. Volume ceiling

One short line is the norm. Never a multi-paragraph docstring, nor a multi-line block where one
line carries the point. A block over three lines needs a reason you can state; absent one, cut it.

## 5. Docstrings

A docstring gives the caller the CONTRACT the signature cannot: what the method guarantees, what
it assumes, what it raises, units and side effects. Never one restating the method name
(`"""Compute the total."""` on `_compute_total`), never a parameter list the names and field types
already tell you.

Odoo: a `_compute_*` / `_inverse_*` / `_search_*` / `@api.constrains` / `@api.onchange` method
needs a docstring only when the RULE it enforces is not derivable from the code. An override of a
core method states WHY it exists - the behavior it adds - never that it is an override.

## 6. Where a comment IS required

- `cr.commit()` outside the framework - why it is necessary, correct, and does not break the
  transaction.
- An always-invisible field in a view, on the series whose lint gate demands that XML comment.
- A deliberate deviation from a convention these guidelines impose.

## Precedence over the upstream lines

The verbatim coding-guidelines extractions say to document your code with docstrings on methods
and JSDoc on functions. Both are a PERMISSION, not a quota - neither requires a docstring on a
method whose name already carries the contract. Where they and this file differ, THIS contract
governs. (`@override` naming the parent it overrides survives: the code cannot show that.)

## In review

| Finding | Severity |
|---|---|
| Attribution, narration, provenance, before/after, or an unshippable reference | MED |
| Comment or docstring that only restates what the code or identifier says | LOW |
| Missing comment where a non-obvious, load-bearing constraint is invisible | MED |
