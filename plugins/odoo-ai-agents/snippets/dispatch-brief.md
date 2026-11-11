# Dispatch brief (what a caller hands an agent it launches)

A brief is a few `KEY: value` lines in the launch prompt. The agent arrives knowing its trade and
its own contract; the brief gives it what only the caller knows.

## What a brief carries

1. **Scope, intent, goal, key results - not the method.** State the outcome wanted and why, what
   is in and out of scope, and what done looks like. Leave out step sequences, tool or command
   chains, a design or fix direction, lists of points to inspect, domain heuristics, version facts
   and text copied from a file the agent reads. The agent owns its method; a prescribed one
   overrides its judgement and hides the cases you did not think of.
2. **Evidence, not your conclusion.** What you observed travels as something the agent can open: a
   path and line, a log path, a failing test id with its first traceback line, a finding in a
   report file. Your diagnosis, suspected cause or preferred fix stays out; when it must be said,
   it is one line labelled `HYPOTHESIS:`. This binds a fix round and a re-dispatch most, because
   there you hold an analysis: send the findings file and the evidence, and let the agent find the
   cause.
3. **Resolved values.** Pass the actual path, profile, version, interpreter, `SHARE_DIR` and
   `ISOLATE_DIR`, never "read X to find it". A line number, SHA or count is true only in the tree
   it was measured in: give it with where and at which commit; the receiver re-measures and
   reports a mismatch.
4. **One kind of work per dispatch.** Split by kind (research, write code, write tests, provision,
   run, commit), not by size.
5. **One screen.** One line per field, about 40 lines in all. Over that, cut method, never a field:
   a missing field costs a `NEEDS_CONTEXT` round trip.

An unnamed worker (an anonymous fork or spawn with no agent definition) holds no method: paste the
procedure it needs. A fork inherits your context, not your role: say that it researches read-only,
acquires no lease, launches no agent and writes no file. For Odoo or git work a plugin specialist
comes before a general-purpose agent.

## Universal skeleton

Fields are content slots; a skill's own template may name one differently (`REQUEST` for the
objective), but the content is there.

| # | Field | When | Value |
|---|---|---|---|
| 1 | `OBJECTIVE` | always | the outcome, as an end state or a question |
| 2 | `WHY` | always, one line | the reason upstream; lets the agent judge an edge you did not cover |
| 3 | `SCOPE` | non-trivial work | what is in, what is out |
| 4 | `INPUTS` | always; `none yet` when nothing exists | absolute paths of prior artifacts under their usual keys (`DESIGN_DOC`, `MASTER_DESIGN_DOC`, `SRS`, `RECON`, `SURVEY`, `GAP_MATRIX`, `ORACLE_PATH`, `CATALOG_PATH`, `DIFF_PATH`); prior findings as `file:line` |
| 5 | `WORKTREE_PATH` | the work writes git-tracked files | absolute; the worker receives it and never creates it. `SHARE_DIR` and `ISOLATE_DIR` go with it, resolved once against that root (`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` § Cross-worktree dispatch); `BASE` when the agent must know the base ref |
| 6 | `ACCEPTANCE` | always | a pointer, never a restatement: the design or SRS criteria for a designer or coder, the immutable oracle for a tester, the raw requirement only for the QA planner |
| 7 | `DELIVERABLE`, `RETURN` | always | the artifact, where it lands, what the final message contains |
| 8 | `CONSTRAINTS` | when any | hard boundaries: read-only, do not commit, paths not to touch, human gates, confidentiality |
| 9 | `INSTANCE_HANDLE` | instance work | the handle, or `none provisioned` |
| 10 | `RETURN_BUDGET` | research | a cap on the returned summary |
| 11 | `RUN_ID` | a run owns the dispatch or a lease will be taken; else `none` | the run's ownership identity, forwarded unchanged to every descendant; a dispatched agent never invents it |

Every launch passes `model`: the lowest tier whose row matches the work in
`${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § Model-tier selection. `ODOO VERSION`
and `PROFILE` travel per `${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`. A brief has
no reply address: the agent's report returns to its launcher by itself.

## Family deltas

Added to the skeleton for the agent you launch.

| Family | The caller also supplies |
|---|---|
| Designer, planner (`odoo-solution-architect`, `odoo-planner`) | the architecture to fit inside; which decisions are settled and which need a trade-off; the interfaces other modules rely on; whether a human gate precedes code |
| Coder (`odoo-coder`, `odoo-frontend-coder`) | `MODULES` in dependency order, `name @ path` each; `RECON`, `IMPACT_MAP`, `SRS`, `DOMAIN`, `BUILD_TIER`, `DESIGN_DOC`, `SURVEY`, each a value or `none`, never omitted; for `odoo-coder`, `INSTANCE_HANDLE` or `SELF_PROVISION: worktree-addons`, never both, and `SERVER_WIDE` with a handle; `COMMIT: caller` when the caller commits; the caller's `CONSTRAINTS` and, in adapt mode, `INTENT`, unchanged. On a re-dispatch, `PRIOR ATTEMPT`: what the earlier pass returned and the evidence of what is wrong now |
| Reviewer (`odoo-code-reviewer`, `odoo-ui-reviewer`) | the target (worktree or branch, and the diff range) and `CHANGED_SET`; the dimensions in scope this pass and those a sibling pass covers; `DIFF_PATH` only as a plain diff whose totals match the numstat. Never where you suspect the defect is |
| Diff comparator (`odoo-diff-comparator`) | `mode` (`rebase` or `upgrade`) and `slug`; rebase: `diff_path`, `diff_scope`, `intents_dir`; upgrade: `diff_scope`, `repo_root`, `source_version`, `target_version` |
| Tester, QA (`odoo-test-writer`, `odoo-qa-planner`, `odoo-qa-tester`) | the oracle or scenario file, expected results fixed before execution; the roles; `INSTANCE_HANDLE` where one exists; for the test writer, `CHANGED CODE` and `CROSS-MODULE ASSERTIONS`. The QA planner gets the raw requirement, never the implementation. A reported red carries the test id and the first traceback line; "pre-existing" is measured by the same test on the clean base |
| Doc writer (`odoo-doc-writer`, `odoo-doc-site-writer`) | `MODE` or the page-plan group; the audience source (`DOMAIN` or `SRS`); the languages; the grounding files already written |
| Marketer (`odoo-marketer`) | `MODE`; for `copy`, the channel, topic and language; `BUYER PROFILE` or `TARGET MARKET`; the grounding files |
| Translator (`odoo-translator`) | one language, the module or cluster, the series; `GLOSSARY_PATH`; the `.po` and `.pot` paths; the `INSTANCE_HANDLE` and `BUILD_SHAPE` of the build they came from |
| Icon designer (`odoo-icon-designer`) | `MODULE_PATH`, absolute; `odoo_version`; palette values when the brand differs from the default; `INSTANCE_HANDLE` when the module is installed |
| Instance ops (`odoo-instance-ops`) | the operation, series, modules, demo and languages, `addons_path`; `GATE_ROLE` on every test run; `INSTANCE_HANDLE` when one exists |
| Video producer (`odoo-video-producer`) | `MODE`, `STORYBOARD`, `LANGUAGES`, `AUTHOR PROFILE` or `none`, `BUDGET_MARGIN`; `INSTANCE_HANDLE` for `record` |
| Survey, analyst (`odoo-backend-debugger`, `odoo-ui-debugger`, `odoo-impact-recon`, `odoo-intent-extractor`, `odoo-installable-prober`, `odoo-gap-analyzer`) | the ask as an open question; findings as a file or inline; that uncertainty is reported, never guessed |

Git agents take their brief from the git toolkit's own skill, not from this file.
