<!-- SSOT snippet. Referenced (not copy-pasted) by odoo-coder / odoo-frontend-coder (write to
     spec on the first pass), odoo-code-reviewer (cite the violated rule), odoo-solution-architect
     (the design IS the coder's spec), and injected into the odoo-coding dispatch brief so a
     dispatched coder is told at execution time. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/read-before-write-contract.md. -->

# Read-Before-Write Contract (conform on the first pass)

You are about to write or change Odoo code. The official Odoo coding guidelines are extracted,
per-version and self-contained, under
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/`. You MUST read the topic files for the
work BEFORE writing a line - not after, against a checklist. Writing first and patching later
churns the diff, fights the reviewer, and (in a stable series) violates the "keep diffs minimal"
rule the guidelines themselves impose.

## The contract

1. **Resolve the Odoo version first** (from `.odoo-ai/context.md`, the discovered `__manifest__.py`,
   or what the user stated). The guidelines are version-pinned and do NOT inherit across series; a
   v17 rule may be wrong for v18. If the version cannot be resolved, resolve it before writing - a
   precondition, not optional.
2. **Open the version index:** `coding_guidelines/<version>/INDEX.md` (e.g. `17.0/INDEX.md`). It
   carries a "By task" table that maps your task to the exact files to read.
3. **Read the by-task files for THIS change, then write to spec on the first pass.** Map by stack:
   - **Backend (Python / XML / ORM):** `python.md` (imports, ORM idioms, `_()` translation form),
     `naming.md` (model `_name`, class, field `_id`/`_ids`, method prefixes), `model-ordering.md`
     (attribute order inside a Model class); `xml.md` for views/data; `module-structure.md` for a
     new module; `security.md` (secure-coding pitfalls: sudo, SQL injection, XSS, safe_eval).
   - **Frontend (JS / OWL / QWeb / SCSS):** `javascript.md` (JS/OWL conventions) and `scss.md`
     (SCSS/CSS properties order, `$o-[root]-[element]-[property]` naming, `:root` rules). If the
     change also touches Python controllers or view XML, the backend files above stay in force.
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
