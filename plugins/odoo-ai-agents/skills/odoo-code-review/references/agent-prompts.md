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
Return the compact scope fields: slug, target_kind, review_root, base_ref,
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
DESIGN_DOC: <path to .odoo-ai/designs/<slug>-<date>.md> (present only when odoo-solution-architect
ran). When DESIGN_DOC path is provided (non-null): MANDATORY - Read it, verify the code against
"## 1. Intent & Business Value" and "## 9. Acceptance Criteria", and emit the "### TDD Conformance"
block. Skipping TDD verify when DESIGN_DOC is present is a review defect. When DESIGN_DOC is absent
(null/omitted): OMIT the TDD Conformance block and review intent from this brief alone.
Optional: COVERAGE_BASELINE: <test_coverage_audit result> (from scoper). Attach as context.
UI_REVIEW: <delegated | absent> - pass `delegated` when scoper set needs_ui_review for this module:
review NON-rendered concerns + the SOURCE correctness of the view layer only (XPath resolves, arch
well-formed, no dead JS module import, SCSS compiles); the rendered-UI verdict (appearance/UX/a11y/
runtime) is owned by the Phase A.5 odoo-ui-reviewer - do not duplicate it. When the module's
needs_ui_review is `candidate`, also confirm view-binding via OSM and record `ui_review_required` in
<module>.md. Omit this line when needs_ui_review=false.
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
.odoo-ai/reviews/<slug>-<date>/ - each <module>.md AND each ui-review-<module>.md (rendered-UI
findings from Phase A.5) so the integration verdict accounts for UI findings. Write _synthesis.md there.
Output contract: per odoo-code-reviewer agent SSOT (${CLAUDE_PLUGIN_ROOT}/agents/odoo-code-reviewer.md)
- include overall VERDICT (APPROVE/REQUEST_CHANGES) and SCORE 0-100 aggregated across all modules.
DESIGN_DOC: <path> - When provided (non-null): MANDATORY - verify the closure satisfies the design's
"## 9. Acceptance Criteria" solution-level criteria and emit the "### TDD Conformance" block.
Skipping TDD verify when DESIGN_DOC is present is a review defect. When absent (null/omitted):
OMIT the TDD Conformance block.
Optional: COVERAGE_BASELINE: <test_coverage_audit result at module level from scoper> - context only.
Optional: COVERAGE_CHECK: <tests_covering results at model-edge level from main> - context only.
Return a summary + path.
```

## UI reviewer (odoo-ui-reviewer, sonnet) - conditional, Phase A.5

Dispatch once per module with `needs_ui_review` (`true` or `candidate`) when an instance is reachable.

```
USER LANGUAGE: <e.g. Vietnamese>
ODOO_VERSION: <e.g. 17.0>
Review the RENDERED UI for module `<module>` on these screens: <affected_screens - view/action/menu
xmlids from scoper>. Resolve instance_base_url from .odoo-ai/context.md (else ~/.odoo-ai/instances.toml);
browser headless by default.
Rate the six lenses (aesthetics, functional correctness, runtime stability, accessibility, performance,
design-system/theme fidelity) per your agent SSOT (${CLAUDE_PLUGIN_ROOT}/agents/odoo-ui-reviewer.md).
DESIGN_DOC: <path | absent> - when present (non-null): MANDATORY - verify the UI-observable acceptance
criteria and emit the "### TDD Conformance" block. When absent: OMIT it.
ARTIFACT_DIR: .odoo-ai/reviews/<slug>-<date>/
ARTIFACT_FILE: ui-review-<module>.md - write your six-lens verdict THERE (not your own default path) so
Phase B synthesis can read it.
Return a short summary (per-lens PASS/WARN/FAIL + top finding) and the artifact path.
```

## Domain synthesis (odoo-code-reviewer, opus) - large sets only (Phase B domain-partition)

### Per-domain pass (one per business-domain bucket)

```
MODE=synthesis. DOMAIN: <domain name>. Modules in this domain: [<m1>, <m2>, …]. review_root: <abs-path>.
Read ONLY this domain's per-module reports (<module>.md + ui-review-<module>.md) in
.odoo-ai/reviews/<slug>-<date>/. Compute the dependency closure WITHIN this domain
(forward module_inspect(name='<m>', method='dependencies', odoo_version='<version>'), reverse impact_analysis) and review cross-module
integration risk inside the domain only. Write domain-<d>.md there.
Output contract: per odoo-code-reviewer agent SSOT (${CLAUDE_PLUGIN_ROOT}/agents/odoo-code-reviewer.md)
- include VERDICT (APPROVE/REQUEST_CHANGES) and SCORE for this domain. Return a summary + path.
```

### Final cross-domain pass (one, after all per-domain passes)

```
MODE=synthesis. Domains: [<d1>, <d2>, …]. review_root: <abs-path>.
Read every domain-<d>.md in .odoo-ai/reviews/<slug>-<date>/. Compute CROSS-DOMAIN closure
(inter-domain field/API contracts, manifest depends + data load-order across domains, ripple between
domains). Write _synthesis.md with the overall VERDICT (APPROVE/REQUEST_CHANGES) + SCORE aggregated
across ALL domains. The final verdict + score MUST aggregate the per-module severity counts carried
in each domain-<d>.md (not only domain-level integration findings), so a large-set PR still reflects
every per-module CRITICAL/HIGH. Return a summary + path.
DESIGN_DOC: <path | absent>
When provided (non-null): MANDATORY - verify the closure satisfies the design's "## 9. Acceptance
Criteria" solution-level criteria and emit the "### TDD Conformance" block. Omit when absent.
```

Each agent: restricted tools, writes only its own report artifact, does NOT spawn subagents, does NOT invoke Skill tool.
