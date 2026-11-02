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
  for safety", "as requested in review": noise the moment the change merges.
- **Process narration** - "first tried X, then Y", "after investigating", "refactored from".
- **Provenance** - ticket/PR numbers, dates, author or agent names, "used by X", "added for the Y
  flow". Those belong in the commit message.
- **Before/after** - "no longer", "previously", "the new behavior". (An EXTERNAL Odoo version fact
  such as an API removed in a given series is domain knowledge - keep it.)
- **Unshippable references** - anything outside the repository the code ships in: a design doc,
  worklog, review, oracle or plan under the run's state dir, an absolute or worktree path, a run
  id, slug or instance handle - and any document inside it (a README, a guide, a docs page).
  State the reason itself, never where you read it.
- **Volatile measurements** - a duration, a query or test count, "currently": true today, stale
  tomorrow.
- **Commented-out code**, and banner or separator comment blocks.

These bans bind the lines a change adds; an existing reference stays until its target is deleted,
and a review reads only the added lines.

## 4. Volume ceiling

One short line is the norm. Never a multi-paragraph docstring, nor a multi-line block where one
line carries the point. A block over three lines needs a reason you can state; absent one, cut it.
A docstring's field list (§ 5) is the contract, not a block in this sense.

## 5. Docstrings

A docstring gives the caller the CONTRACT the signature cannot: what the thing is for, what it
guarantees and assumes, what it returns, what it raises and when, units and side effects (a
database write, a bus message, a commit). It says WHAT, never HOW: changing the implementation
must not require changing the docstring. Never one restating the name (`"""Compute the total."""`
on `_compute_total`).

A Python docstring - module, class, method, function - is written in reStructuredText field
syntax on every series:

```python
def action_publish(self, when=None):
    """Publish the page and notify its followers.

    :param when: publication time; ``None`` publishes now
    :return: the published pages
    :raises UserError: when the page has no space
    """
```

Markers: `:param name:`, `:type name:`, `:return:`, `:rtype:`, `:raises Exc:`; inline code in
double backticks. A parameter whose name and type already say what it is gets no `:param:` line;
one with a non-obvious meaning, a unit, a default sentinel or a type the signature does not show
gets one. `Args:` / `Returns:` / `Raises:` sections (Google or NumPy style), and free prose where a
field belongs, are not written. JavaScript keeps the JSDoc of core Odoo of the same series.

Odoo: a `_compute_*` / `_inverse_*` / `_search_*` / `@api.constrains` / `@api.onchange` method
needs a docstring only when the RULE it enforces is not derivable from the code. An override of a
core method states WHY it exists - the behavior it adds - never that it is an override.

A constant used in one place is written where it is used; a string a user sees is wrapped for
translation. A cleanup that strips a requirement label or narration from a comment deletes the
line unless a reason still holds - never rewords it; docstring-heavy old code is shortened, and a
deleted docstring is never restored.

## 6. Where a comment IS required

- `cr.commit()` outside the framework - why it is necessary, correct, and does not break the
  transaction.
- An always-invisible field in a view, on the series whose lint gate demands that XML comment.
- A deliberate deviation from a convention these guidelines impose.

## Precedence over the upstream lines

The coding-guidelines line "document your code" is a PERMISSION, not a quota: it requires no
docstring on a method whose name already carries the contract. Where it and this file differ,
THIS contract governs. (`@override` naming the parent survives: the code cannot show that.)

## In review

| Finding | Severity |
|---|---|
| Attribution, narration, provenance, before/after, or an unshippable reference | MED |
| Comment or docstring that only restates what the code or identifier says | LOW |
| Python docstring in Google or NumPy style (`Args:`, `Returns:`, `Raises:`), or prose where a field belongs | LOW - the fix is the rst field form of § 5 |
| Missing comment where a non-obvious, load-bearing constraint is invisible | MED |
