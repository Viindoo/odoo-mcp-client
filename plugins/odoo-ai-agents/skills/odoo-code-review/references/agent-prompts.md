# odoo-code-review - Agent Dispatch Prompt Templates

## Scope agent (odoo-review-scoper, sonnet)

```
TARGET: <local | worktree:<abs-path> | pr:<number-or-url>>
BASE: <base-ref, default master>
odoo_version: <e.g. 17.0>
USER LANGUAGE: <e.g. Vietnamese>

Scope this review per your full I/O contract (${CLAUDE_PLUGIN_ROOT}/agents/odoo-review-scoper.md).
Resolve the diff, detect modules (dirs with __manifest__.py), run test_coverage_audit per module,
detect any design doc, determine fanout (single|multi), and write the compact scope file to
.odoo-ai/reviews/<slug>-<date>/_scope.md.
Return the compact scope fields: slug, target_type, review_root, base_ref,
modules[{name,path}], design_doc, coverage_baseline, pr (or null), fanout.
```

## Per-module reviewer (sonnet)

```
MODE=per-module. Review ONLY the changes in module `<module>` at `<path>` (read files at
review_root=<abs-path> from scoper - do NOT read from master or cwd unless review_root matches).
Also do a LIGHT bidirectional-impact pass (${CLAUDE_PLUGIN_ROOT}/snippets/bidirectional-impact.md):
the direct upstream it depends on + direct downstream that depends on it - deep transitive closure
stays the synthesis job, but flag an obvious cross-module break even in single-module review.
Check the change against ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md
(multi-company/branch, generic-before-localization, app-menu) and flag a behavior change with no
protecting test.
Optional: DESIGN_DOC: <path to .odoo-ai/designs/<slug>-<date>.md> (present only when
odoo-solution-architect ran). If given, Read it and verify the code against its
"## 1. Intent & Business Value" and "## 9. Acceptance Criteria"; emit the "### TDD Conformance"
block. If absent, review intent from this brief alone.
Optional: COVERAGE_BASELINE: <test_coverage_audit result> (from scoper). Attach as context.
Artifacts dir: .odoo-ai/reviews/<slug>-<date>/ - write your report to <module>.md there.
Output contract: per odoo-code-reviewer agent SSOT (${CLAUDE_PLUGIN_ROOT}/agents/odoo-code-reviewer.md)
- include VERDICT (APPROVE/REQUEST_CHANGES) and SCORE 0-100 in your report.
Return a 5-line summary (counts by severity + top finding + verdict + score) and the artifact path.
```

## Synthesis reviewer (opus)

```
MODE=synthesis. Changed/added modules: [<m1>, <m2>, …]. review_root: <abs-path from scoper>.
Read all files at review_root - do NOT read from master or cwd unless review_root matches.
Compute the dependency closure -
forward via module_inspect(name=<module>, method='dependencies', odoo_version='<version>') transitively, reverse via impact_analysis -
and review CROSS-MODULE integration risk only (override conflicts, MRO, inter-module contracts,
depends/load-order, ripple to dependents). Read the per-module reports already in
.odoo-ai/reviews/<slug>-<date>/. Write _synthesis.md there.
Output contract: per odoo-code-reviewer agent SSOT (${CLAUDE_PLUGIN_ROOT}/agents/odoo-code-reviewer.md)
- include overall VERDICT (APPROVE/REQUEST_CHANGES) and SCORE 0-100 aggregated across all modules.
Optional: DESIGN_DOC: <path> - if given, also verify the closure satisfies the design's
"## 9. Acceptance Criteria" solution-level criteria; emit the "### TDD Conformance" block.
Optional: COVERAGE_BASELINE: <test_coverage_audit result at module level from scoper> - context only.
Optional: COVERAGE_CHECK: <tests_covering results at model-edge level from main> - context only.
Return a summary + path.
```

Each agent: restricted tools, writes only its own report artifact, does NOT spawn subagents, does NOT invoke Skill tool.
