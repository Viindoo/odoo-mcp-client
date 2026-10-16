# Scenario 3 - seeded defects, review recall

**Setup.** A sample module with a known list of defects planted before the run, including:
- a `VERSION RULES APPLIED` block citing a guideline heading that does not exist;
- a reference to a symbol owned by a module outside the `depends` closure;
- an `@api.depends` that omits a field the compute reads;
- a `sudo()` without a reason;
- a test that asserts display text.

**Run.** `/odoo-code-review worktree:<path>`.

**Measure:** per planted defect, whether R1 or R2 reported it (HIGH or CRITICAL), its file:line,
and every finding that is not a planted defect (false positives), compared with the same review
run by the previous release's reviewer on the same module.

**Pass when** recall of HIGH/CRITICAL is not below the baseline and the false-positive count is
not above it.
