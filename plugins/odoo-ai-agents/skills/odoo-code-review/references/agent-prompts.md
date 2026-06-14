# odoo-code-review — Agent Dispatch Prompt Templates

## Per-module reviewer (sonnet)

```
MODE=per-module. Review ONLY the changes in module `<module>` at `<path>`.
Also do a LIGHT bidirectional-impact pass (${CLAUDE_PLUGIN_ROOT}/snippets/bidirectional-impact.md):
the direct upstream it depends on + direct downstream that depends on it - deep transitive closure
stays the synthesis job, but flag an obvious cross-module break even in single-module review.
Check the change against ${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md
(multi-company/branch, generic-before-localization, app-menu) and flag a behavior change with no
protecting test.
Artifacts dir: .odoo-ai/reviews/<slug>-<date>/ — write your report to <module>.md there.
Return a 5-line summary (counts by severity + top finding) and the artifact path.
```

## Synthesis reviewer (opus)

```
MODE=synthesis. Changed/added modules: [<m1>, <m2>, …]. Compute the dependency closure —
forward via module_inspect(method='dependencies', odoo_version='<version>') transitively, reverse via impact_analysis —
and review CROSS-MODULE integration risk only (override conflicts, MRO, inter-module contracts,
depends/load-order, ripple to dependents). Read the per-module reports already in
.odoo-ai/reviews/<slug>-<date>/. Write _synthesis.md there. Return a summary + path.
```

Each agent: restricted tools, writes only its own report artifact, does NOT spawn subagents, does NOT invoke Skill tool.
