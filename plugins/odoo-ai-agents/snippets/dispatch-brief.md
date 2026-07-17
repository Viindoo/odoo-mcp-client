<!-- SSOT snippet. The single home for the CALLER-side dispatch-brief schema - how any
     spawner (main agent, a dispatching skill, or a nested coordinator) fills the dispatch
     prompt when it dispatches a specialist agent. This is the input-side counterpart
     to `worker-brief.md` (worker-side behavior the leaf must execute). Read BY PATH by
     non-leaf spawners composing a dispatch prompt; NEVER inlined verbatim into a hard-leaf
     brief - a leaf self-checks against only the family-delta field list carried inline in its
     own body. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/dispatch-brief.md. -->

# Dispatch Brief (caller-side template)

**This file is the SSOT for the CALLER-side dispatch brief - the content of the dispatch
prompt a spawner sends to a specialist agent.** Fields are content SLOTS in `KEY: value`
form, not literal headings. Reference existing homes for intent/acceptance/artifacts - `DESIGN_DOC`,
`ORACLE_PATH`, worklog, etc. - do not restate their content here or in a filled brief.

This file is **READ BY PATH** by non-leaf spawners while they compose a dispatch prompt. It is
**NEVER inlined verbatim into a hard-leaf brief**: a leaf does not author dispatch prompts, so it
does not need the caller schema - it self-checks against the family-delta field list already
carried inline in its own body (see `## Brief self-check` below). This is the opposite of
`worker-brief.md`, which IS inlined into leaves because it is worker-side behavior the leaf must
execute.

## Universal skeleton (10 fields)

| # | Field | ALWAYS / COND | Definition |
|---|-------|----------------|------------|
| 1 | `OBJECTIVE` | ALWAYS | The outcome as an end-state/question, not a procedure. |
| 2 | `WHY` | ALWAYS (1 line) | Upstream reason; lets the agent judge under-specified edges and push back. Point at the worklog for detail; do not restate it. |
| 3 | `SCOPE` (in / out) | ALWAYS (non-trivial tasks) | Explicit include + exclude list. |
| 4 | `INPUTS` (artifact paths) | COND - ALWAYS when priors exist; `none yet` is a valid explicit value | Absolute paths to survey/research/gap/design/oracle files + specific prior findings (`file:line`). Reuse existing key names: `DESIGN_DOC`/`MASTER_DESIGN_DOC`, `GAP_MATRIX`, `SCENARIOS_PATH`/`ORACLE_PATH`, `CATALOG_PATH`, `diff_path`. |
| 5 | `WORKTREE_PATH` (+ `BASE` COND) | COND - `WORKTREE_PATH` required whenever the task mutates git-tracked files; `BASE` only when the agent must know the base ref (e.g. rebase/adapt mode) | Absolute worktree path + (conditionally) base ref/branch. MUST reuse the literal `WORKTREE_PATH` token (grepped verbatim elsewhere; a new name silently misses consumers). The worker RECEIVES it, never creates it - worktree creation belongs to git-toolkit. |
| 6 | `ACCEPTANCE` (by pointer) | ALWAYS | Testable yes/no "done" conditions, given as a POINTER, never restated: coder/designer -> `DESIGN_DOC` S9; QA-tester -> the immutable `ORACLE_PATH`; QA-planner -> the raw `REQUIREMENT`/intent ONLY (never the implementation or a pre-derived oracle - preserves its independence). |
| 7 | `DELIVERABLE` + `RETURN` | ALWAYS | What artifact(s), where they land, and what the final chat message must contain. Reuse `OUTPUT_DIR`/`REPORT_PATH`/`ARTIFACT_DIR` where a family already names them. |
| 8 | `CONSTRAINTS` | COND | Hard boundaries (read-only, do-not-commit, must-not-touch paths, human-confirm gates, confidentiality). A boundary, never a procedure. |
| 9 | `MODEL`/`EFFORT` hint | COND - only when the caller holds signal the dispatcher lacks | Tier/effort override; `INSTANCE_HANDLE` forwarded when one exists (else the explicit value `none provisioned`). |
| 10 | `RETURN_BUDGET` | COND - recommended for research/analysis | Cap on the returned summary length/time-box. |

`odoo_version` and `viindoo_profile` are NOT skeleton fields - they are carried per
`${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md` (resolve the Tier-2 SHARE dir per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`'s resolve-capture-substitute protocol
and read `context.md` there first - never a bare `.odoo-ai/context.md` literal; ask the caller
only when absent). This file references that snippet rather than re-specifying those two fields.

## Role-family deltas (additive on the skeleton)

Each `odoo-ai-agents` agent body carries ONLY its family's delta + a one-line non-load-bearing
pointer back to this file - never the full skeleton table.

### Designer / planner

`odoo-solution-architect`, `odoo-planner`, `odoo-doc-planner`:

- Pointer to the CURRENT architecture/constraint snapshot to fit inside.
- Which decisions need an ADR-style tradeoff vs are already-settled.
- Non-negotiable interfaces other modules assume.
- Whether a human gate precedes code.
- `ACCEPTANCE` resolves to the design doc's S9 (skeleton field 6).
- `PEERS` - same-layer sibling addresses the lead brokered for bounded peer reconciliation; `none`
  when the layer has one child.

### Coder

`odoo-coder` (coordinator/spawner - see the SPAWNER self-check variant below, not the leaf one),
`odoo-backend-coder`, `odoo-frontend-coder`:

- `RED_TEST_PATH` - the failing test(s) `odoo-test-writer` already authored (hand over the failing
  test, not a spec).
- The module/disjoint file-set boundary.
- `INSTANCE_HANDLE`, or the explicit value `none provisioned`.
- `DESIGN_DOC` to follow STRUCTURALLY - never inlined pseudocode.
- `WORKTREE_PATH` mandatory; `BASE` CONDITIONAL (only when the coder must know the base ref for a
  rebase/adapt mode - a normal build's worktree already encodes the base).

### Reviewer / auditor

`odoo-code-reviewer`, `odoo-ui-reviewer`:

- The target diff/worktree/PR pointer (never bare "review the code").
- Which audit DIMENSIONS are in scope THIS pass - name them; never default to "everything".
- Name the verdict/severity taxonomy the caller expects back - static code review -> the unified
  rubric `review-severity-rubric.md` (CRITICAL/HIGH/MED/LOW); rendered-UI review -> its six-lens
  PASS/WARN/FAIL verdict.
- The coverage baseline, so a dimension a sibling pass already owns is not re-run.
- `CHANGED_SET`/`SCOPE_FILES` for diff-scoping (the diff-scoped code reviewer).

### Diff comparator (rebase / upgrade absorption)

`odoo-diff-comparator`:

- `mode` - `rebase` or `upgrade`; determines which of the remaining fields apply and which output
  it emits.
- Rebase mode: `diff_path` (the diff/range-diff file the orchestrator wrote via
  `git-toolkit:git-ops`, read-only - this agent is git-free) + `diff_scope` (the two refs, e.g.
  `new-base...feature-ref`) + `intents_dir` (per-commit intent records from
  `odoo-intent-extractor`).
- Upgrade mode: `diff_scope` (module path/name) + `repo_root` (local source root for `Read`/`Grep`,
  never git) + `source_version`/`target_version`.
- `slug` - run slug used to derive its output file paths.
- Its OWN output vocabulary - never the code-review severity rubric and never `CHANGED_SET`/
  `SCOPE_FILES`: upgrade-mode classification `KEEP`/`DELETE-absorbed`/`OBSOLETE`/`REWRITE(api|model)`/
  `MERGE`/`SPLIT`/`RECONCILE`; rebase-mode outcome buckets (a) already-present / (b) adapt /
  (c) re-implement / (d) drop, plus `range_diff_verdict: PASS | FAIL` for the P10 verify pass.

### Tester / QA

`odoo-test-writer`, `odoo-qa-planner`, `odoo-qa-tester`:

- The oracle/scenario file - expected results chosen BEFORE execution.
- Environment / `INSTANCE_HANDLE`.
- Roles/personas.
- Adjudication vocabulary `PASS`/`FAIL`/`UNVERIFIED` + evidence.
- Exception - `odoo-qa-planner`'s input is the raw `REQUIREMENT`/intent, NOT the implementation.

### Doc-writer

`odoo-user-doc-writer`, `odoo-marketing-writer`, `odoo-doc-scenarist`, `odoo-translator`:

- Target AUDIENCE/persona.
- Locale/language list.
- Grounding source (feature catalog / walkthrough) - never invent claims.
- Output format (`rst`/`html`/video-plan/`po`/`svg`).

### Icon designer

`odoo-icon-designer`:

- `MODULE_PATH` - the absolute module path (never a bare module name).
- `BRIEF` palette hex values (`BG`/`FG`) when a brand differs from the category-hue default.
- `odoo_version` - drives the era-correct visual style and the PNG-only (v8-v18) vs
  PNG+SVG+manifest-key (v19) gate.
- No locale/language list and no feature-catalog grounding - this agent is standalone (OSM +
  disk), not audience-facing prose.

### Instance / ops

`odoo-instance-ops`:

- `INSTANCE_HANDLE` - the handle to create/drive/report on.
- Target series/version.
- The module list to init/update.
- Demo-data + languages flags.
- `addons_path`.
- The "provision-once / forward-everywhere" rule (`instance-handle-contract.md`).
- Carries NO git ref / force-push / commit-convention fields - this family provisions databases and
  runs zero git.

### Survey / analyst

`odoo-backend-debugger`, `odoo-ui-debugger`, `odoo-review-scoper`, `odoo-intent-extractor`,
`odoo-installable-prober`, `odoo-gap-analyzer`, `odoo-feature-cataloger`, `odoo-doc-scoper`:

- The ask framed as an open QUESTION, not a scripted search-command sequence.
- Structured findings FILE vs inline chat answer.
- Explicit instruction to report uncertainty/confidence, never present a guess as fact.

### Git family - not here

The **Git** family delta (base ref + target ref; safety-gate for destructive rewrite/force-push;
"detect the commit convention, do not invent one"; what must NOT be touched) lives ONLY in
`git-toolkit`'s `git-nesting-protocol.md` - it is intentionally NOT reproduced in this file
(cross-plugin boundary; `git-toolkit` cannot depend on `odoo-ai-agents`).

## Brief self-check

Two reusable variants of the same clause. Copy the one matching the target agent's `spawn_class`
verbatim into its body under the heading `## Brief self-check` (never `## When to invoke` - banned
by `test_agent_body_convention.py`).

### LEAF variant (every hard-leaf agent)

```markdown
## Brief self-check

(run before any work)
Confirm the dispatch brief carries `OBJECTIVE`, `ACCEPTANCE` (by pointer), and this family's
required fields (<family fields>). Graduated response, per ODOO-AI-ETHOS #2 ask-vs-self-decide:
- Missing a field with a safe default (small, reversible gap, e.g. `WHY`): PROCEED and state the
  assumption as your first output line.
- Missing `OBJECTIVE`, `ACCEPTANCE`, or a load-bearing family field with no safe default: STOP and
  return `NEEDS_CONTEXT(<field>)` (caller can re-brief) or `BLOCKED(<field>)` (gap is
  irreversible/large). Do not silently guess or degrade.

Full caller-side schema (reference only, not required to resolve): `dispatch-brief.md`.
```

Replace `<family fields>` with the agent's own family-delta field list (e.g. the Coder delta above);
`<field>` in the status calls is the specific missing field name at runtime, not literal text.

### SPAWNER variant (`odoo-coder` only)

`odoo-coder` is a per-module COORDINATOR, not a leaf - `worker-brief.md` explicitly exempts it. Its
`## Brief self-check` is framed for a spawner: it validates its OWN inbound brief, then RE-BRIEFS
each leaf it dispatches by reading this file BY PATH. It must NOT contain the leaf-only "STOP and
return NEEDS_CONTEXT" wording verbatim - that phrasing belongs to a leaf that has no one left to
re-brief.

```markdown
## Brief self-check

(run before dispatching any leaf)
Validate your OWN inbound dispatch brief carries `OBJECTIVE`, `ACCEPTANCE` (by pointer), and the
Coder family's required fields (`RED_TEST_PATH`, module/file-set boundary, `INSTANCE_HANDLE` or
`none provisioned`, `DESIGN_DOC`, `WORKTREE_PATH` [+ `BASE` in rebase/adapt mode]).
- Missing a field with a safe default: PROCEED and state the assumption as your first output line.
- Missing `OBJECTIVE`, `ACCEPTANCE`, or a load-bearing field with no safe default: surface the gap
  to your own caller before dispatching any leaf - do not silently guess or degrade, and do not
  dispatch a leaf on an unresolved brief.

Then RE-BRIEF each leaf you dispatch (`odoo-test-writer`, `odoo-backend-coder`,
`odoo-frontend-coder`): read `dispatch-brief.md` BY PATH, fill the universal skeleton + the target
leaf's family delta, and hand each leaf a self-contained brief - never your own raw inbound brief
passed through unchanged.
```

## How a caller uses it

Any spawner - the main agent, `odoo-coding`, `odoo-code-review`, `odoo-coder`, `run-harness`,
`workflow-chaining`, or any other dispatching skill/agent - reads this file BY PATH, then fills the
universal skeleton + the target agent's family delta into the dispatch prompt. There is **no
verbatim inlining** of this file into a hard-leaf brief: a leaf receives a filled brief, not this
caller schema, and self-checks against the family delta already inline in its own body.
