<!-- SSOT snippet. Referenced (not copy-pasted) by odoo-coder / odoo-frontend-coder (write to
     spec on the first pass), odoo-code-reviewer (cite the violated rule), odoo-solution-architect
     (the design IS the coder's spec), and injected into the odoo-coding dispatch brief so a
     dispatched coder is told at execution time. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/read-before-write-contract.md. -->

# Read-Before-Write Contract (conform on the first pass)

You are about to write or change Odoo code. The official Odoo coding guidelines are extracted,
per-version and self-contained, under
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/`.

**MANDATORY HARD RULE:** do NOT write a single line of a given file type until you have read the
By-task-mapped guideline file + the matching `odoo-version-pivots.md` section for that file type.
Reading the version INDEX 'By task' table first is mandatory; reading ONLY the mapped files is
mandatory. Writing first and patching later churns the diff, fights the reviewer, and (in a
stable series) violates the "keep diffs minimal" rule the guidelines themselves impose.

## The contract

1. **Resolve the Odoo version first** (from `.odoo-ai/context.md`, the discovered `__manifest__.py`,
   or what the user stated). The guidelines are version-pinned and do NOT inherit across series; a
   v17 rule may be wrong for v18. If the version cannot be resolved, resolve it before writing - a
   precondition, not optional.
2. **Open `coding_guidelines/<version>/INDEX.md` first** (e.g. `17.0/INDEX.md`). It carries a
   "By task" table - **use it**: read ONLY the files it maps to the task categories you are
   executing (topic file(s) + any listed snippet + the `odoo-version-pivots §` for that task).
   Do NOT read the whole directory; files for task categories not in scope waste tokens and add
   noise. Domain-knowledge activation (e.g. HR payroll, Accounting) applies within the mapped
   files - read the relevant section, not the whole file.
3. **Read the By-task mapped files for THIS change, then write to spec on the first pass.** The
   INDEX By-task table maps each task category to the exact files - follow it. Reference only:
   Python/ORM tasks typically pull `python.md`, `naming.md`, `model-ordering.md`; XML/view tasks
   pull `xml.md`; new module pulls `module-structure.md`; security tasks pull `security.md`;
   JS/OWL tasks pull `javascript.md`; SCSS tasks add `scss.md`. These are examples - the By-task
   table in the version index is authoritative; do not read a file unless the table maps it to
   your task.
4. **Conform on the first pass - do not write-then-patch.** Naming prefixes, model attribute order,
   import order, ORM idioms, and `_()` form are decided BEFORE you type the code, not corrected
   afterward. Two pre-push static gates act as safety nets: `scripts/verify-backend.sh` (runs
   `pylint-odoo` over changed Python files, catching sql-injection, translation rules, and
   class-merging issues) and `scripts/verify-frontend.sh` (OWL/JS pitfall checks over changed
   JS/XML/SCSS files). Either gate can return `RESULT: CANNOT-VERIFY` (exit 2) when its
   toolchain cannot be resolved - this is **not a pass**; the agent MUST NOT declare done and
   must resolve the toolchain or escalate. These gates catch a mechanical subset; the semantic
   rules (ordering, naming intent, structure, security) are on you, up front.

Each `<version>/` directory is the COMPLETE rule set for that series - read the one matching the
pinned version, never assume another version's conventions carry over.

## Just-in-time re-read (anti-compaction, mandatory)

Context compaction between the read phase and the write phase silently erases version-pivot rules
that differ most between series (e.g. `<list>` vs `<tree>`, `check_access` vs
`check_access_rights`, always-invisible field XML comment).

**Just-in-time re-read:** immediately before writing each file type (the first `.py` file, the
first `.xml` view file, the first `.js` file), re-open ONLY the pivot row for that type in
`odoo-version-pivots.md` and the matching topic file's "Version <N>" section. This is a
30-second targeted re-scan, not a full re-read. It is a compaction hedge.

## VERSION RULES APPLIED (anti-compaction sticky note, mandatory)

Before emitting the FIRST code block of any file type, write a short block titled
`VERSION RULES APPLIED (v<target>):` listing the load-bearing version-specific rules you will
follow, sourced from `odoo-version-pivots.md`. For example:

    VERSION RULES APPLIED (v18):
    - XML: `<list>` not `<tree>`; always-invisible field needs `<!-- invisible: reason -->` XML comment
    - Python: `_compute_display_name` not `name_get()`
    - ACL: `check_access(mode)` not `check_access_rights()` + `check_access_rule()`
    (omit file types not in scope for this task)

This sticky note survives context compaction and is verified by the reviewer. A self-citation
block that does not match the actual code is a HIGH finding.
