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
guideline files the version INDEX's "By file type" table maps to that file type + the matching
`odoo-version-pivots.md` section. Reading that table first is mandatory; reading ONLY the mapped
files is mandatory. Writing first and patching later churns the diff, fights the reviewer, and (in a
stable series) violates the "keep diffs minimal" rule the guidelines themselves impose.

## The contract

1. **Resolve the Odoo version first** per
   `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`. The guidelines are version-pinned
   and do NOT inherit across series; a v17 rule may be wrong for v18. If the version cannot be
   resolved, resolve it before writing - a precondition, not optional.
2. **Open `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/INDEX.md` first**
   (e.g. `17.0/INDEX.md` under that same root). It carries a
   "By file type" table - **use it**: read ONLY the files it maps to the file types you are
   about to write (topic file(s) + any listed snippet + the `odoo-version-pivots §` for that
   type). Do NOT read the whole directory; files for types not in the change waste tokens and
   add noise. Domain-knowledge activation (e.g. HR payroll, Accounting) applies within the mapped
   files - read the relevant section, not the whole file. If
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/INDEX.md`
   does not exist (v8-v13), use `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/14.0/INDEX.md`
   as the closest curated baseline
   AND ground version-specifics via OSM (`set_active_version` + `api_version_diff`/`suggest_pattern`)
   - OSM indexes v8-v19 (see `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/INDEX.md` for
   the fallback rationale).
3. **Read the mapped files for THIS change, then write to spec on the first pass.** The INDEX
   "By file type" table maps each file type to the exact files - follow it. Reference only:
   Python models pull `python.md`, `naming.md`, `model-ordering.md`; view XML pulls `xml.md`; a
   new module pulls `module-structure.md`; security files pull `security.md`; JS/OWL pulls
   `javascript.md`; SCSS adds `scss.md`; tests pull `tests.md`. These are examples - the table in
   the version index is authoritative; do not read a file unless the table maps it to a file
   type you write.
4. **Conform on the first pass - do not write-then-patch.** Naming prefixes, model attribute order,
   import order, ORM idioms, and `_()` form are decided BEFORE you type the code, not corrected
   afterward. Two gates act as safety nets: the backend lint gate (module set:
   `${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`, appended to `--test-tags` in the instance run - catches sql-injection,
   translation rules, class-merging issues; see `ODOO-TESTING.md`) and `scripts/verify-frontend.sh`
   (OWL/JS pitfall checks over changed
   JS/XML/SCSS files). Either gate can return `RESULT: CANNOT-VERIFY` (exit 2) when it did NOT
   run - **not a pass**; never declare done. Fix the PRINTED cause: a missing toolchain is not
   an unresolved Odoo series. These gates catch a mechanical subset; the semantic
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
    - ACL: `check_access(operation)` not `check_access_rights()` + `check_access_rule()`
    (omit file types not in scope for this task)

This sticky note survives context compaction and is verified by the reviewer. A self-citation
block that does not match the actual code is a HIGH finding.
