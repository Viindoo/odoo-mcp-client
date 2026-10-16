# Acceptance scenarios

Seven scenarios prove the plugin's lifecycle on real runs. Each one is run from a checkout with
`claude --plugin-dir ./plugins/odoo-ai-agents` against a declared Odoo instance
(`/odoo-ai-agents:odoo-setup`), and records its measurements in the PR that changes the flow.
A scenario passes only on the evidence it names - launch counts from the worklog, timings, the
review verdict, the acceptance report, the files on disk.

| # | Scenario | Proves |
|---|---|---|
| 1 | [new-feature-three-nodes](01-new-feature-three-nodes.md) | the whole chain from SRS to PR, launch count per tier, review rounds, acceptance verdict, docs a role understands |
| 2 | [standard-change-two-modules](02-standard-change-two-modules.md) | a build node at haiku, databases built from the `depends` closure, red-then-green tests, no false finding from a lagging index, worktree path |
| 3 | [seeded-defects-review-recall](03-seeded-defects-review-recall.md) | R1 + R2 recall of HIGH/CRITICAL defects against the baseline, including a fake guideline citation and a reference outside the closure |
| 4 | [domain-and-audience-labels](04-domain-and-audience-labels.md) | `business_function` and `audience` assigned from the manifest category, including multi-domain requests |
| 5 | [forward-port-at-sonnet](05-forward-port-at-sonnet.md) | a forward-port of one or two modules with the orchestrator at sonnet |
| 6 | [incident-root-cause](06-incident-root-cause.md) | one debugger per incident, time to the proven root cause |
| 7 | [haiku-reads-every-body](07-haiku-reads-every-body.md) | every rewritten agent and skill body answers "what do I do next" at every step with one action |

Thresholds: haiku and sonnet never score below the opus baseline on HIGH/CRITICAL recall; false
positives do not rise; every acceptance criterion holds; `make test` is shorter than the baseline.
