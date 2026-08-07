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
**NEVER inlined verbatim into a hard-leaf brief**: a leaf self-checks against the family-delta
field list already carried inline in its own body (see `## Brief self-check` below) - the opposite
of `worker-brief.md`, which IS inlined into leaves because it is worker-side behavior.

## Universal skeleton (11 fields)

| # | Field | ALWAYS / COND | Definition |
|---|-------|----------------|------------|
| 1 | `OBJECTIVE` | ALWAYS | The outcome as an end-state/question, not a procedure. Governed by ODOO-AI-ETHOS #4 (Outcomes over Procedures) - cited, not restated, here: see `## Brief self-check` below for the site-specific application. |
| 2 | `WHY` | ALWAYS (1 line) | Upstream reason; lets the agent judge under-specified edges and push back. Point at the worklog for detail; do not restate it. |
| 3 | `SCOPE` (in / out) | ALWAYS (non-trivial tasks) | Explicit include + exclude list. |
| 4 | `INPUTS` (artifact paths) | COND - ALWAYS when priors exist; `none yet` is a valid explicit value | Absolute paths to survey/research/gap/design/oracle files + specific prior findings (`file:line`). Reuse existing key names: `DESIGN_DOC`/`MASTER_DESIGN_DOC`, `SURVEY` (opted-in deep-survey findings - explicit `none` when no deep survey ran this session, key still required, same "key must be present" rule as this row), `GAP_MATRIX`, `SCENARIOS_PATH`/`ORACLE_PATH`, `CATALOG_PATH`, `diff_path`. The key itself must be present - omitting it entirely (not even the literal `none yet`) is a load-bearing gap, checked in `## Brief self-check` below. |
| 5 | `WORKTREE_PATH` (+ `BASE` COND) | COND - `WORKTREE_PATH` required whenever the task mutates git-tracked files; `BASE` only when the agent must know the base ref (e.g. rebase/adapt mode) | Absolute worktree path + (conditionally) base ref/branch. MUST reuse the literal `WORKTREE_PATH` token (grepped verbatim elsewhere; a new name silently misses consumers). The worker RECEIVES it, never creates it - worktree creation belongs to git-toolkit. |
| 6 | `ACCEPTANCE` (by pointer) | ALWAYS | Testable yes/no "done" conditions, given as a POINTER, never restated: coder/designer -> `DESIGN_DOC` S9; QA-tester -> the immutable `ORACLE_PATH`; QA-planner -> the raw `REQUIREMENT`/intent ONLY (never the implementation or a pre-derived oracle - preserves its independence). |
| 7 | `DELIVERABLE` + `RETURN` | ALWAYS | What artifact(s), where they land, and what the final chat message must contain. Reuse `OUTPUT_DIR`/`REPORT_PATH`/`ARTIFACT_DIR` where a family already names them. |
| 8 | `CONSTRAINTS` | COND | Hard boundaries (read-only, do-not-commit, must-not-touch paths, human-confirm gates, confidentiality). A boundary, never a procedure - same ODOO-AI-ETHOS #4 governance as `OBJECTIVE` above (cited, not restated). |
| 9 | `MODEL`/`EFFORT` hint | COND - only when the caller holds signal the dispatcher lacks | Tier/effort override; `INSTANCE_HANDLE` forwarded when one exists (else the explicit value `none provisioned`). |
| 10 | `RETURN_BUDGET` | COND - recommended for research/analysis | Cap on the returned summary length/time-box. |
| 11 | `CALLER_ID` (`REPLY_TO`) | ALWAYS | An ADDRESS, never a name. Exactly one of: the literal `main`; the stable spawn `name` you launched this agent under; a raw `agentId`. A skill has no address of its own - it runs inline in whatever context invoked it, so its dispatches carry THAT context's address, `main` only when main is the invoker (full rule: `${CLAUDE_PLUGIN_ROOT}/snippets/context-handoff-protocol.md` "A skill has no address of its own") - never a skill name, never a prose sentence. An agent that will itself dispatch or be messaged MUST have been launched with a stable `name`; its children cannot address it otherwise. Unaddressable, or a send that fails: RETURN INLINE, never wait (`${CLAUDE_PLUGIN_ROOT}/snippets/spawner-completion-contract.md` R3). The `SendMessage`/task-board transport that carries it (`TASK_ID`, `NOTIFY`) is owned by `${CLAUDE_PLUGIN_ROOT}/snippets/agent-team-protocol.md`; the worker-side consumption contract is owned by `${CLAUDE_PLUGIN_ROOT}/snippets/worker-brief.md`. |

`odoo_version` and `viindoo_profile` are NOT skeleton fields - they are carried per
`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`; ask the caller only for what no rung
there answers.

## Two rules that decide whether the brief works

**Every field carries a resolved VALUE.** A field whose value tells the worker to go read a
document is a hidden sub-task it pays before starting. Resolve at dispatch and pass the value: the
actual `SHARE_DIR`, the actual `ISOLATE_DIR`, the actual profile name, the actual addons path, the
actual interpreter path. Cite a document as the RATIONALE for a value you already supplied, never
in place of one. A worker handed resolved paths MUST NOT re-run the resolver from its own cwd.

**One dispatch, one KIND of work.** Split by kind, not by size. A brief that bundles read prior
art, edit a view, author a test, provision an instance, run a suite and commit is six kinds and
will not complete. Length is not the constraint; kind-count is.

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
- `SELF_PROVISION: worktree-addons` or `none` - `odoo-coder`'s INBOUND brief only (the dispatcher's
  per-module worktree-addons carve-out decision; never a separate field on the leaf coders' own
  briefs - see `${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Worktree-addons
  carve-out). MUTUALLY EXCLUSIVE with `INSTANCE_HANDLE`: a brief carrying BOTH is malformed - the
  receiver treats it as the handle case and returns `NEEDS_CONTEXT`.
- `DESIGN_DOC` to follow STRUCTURALLY - never inlined pseudocode.
- `SURVEY` - the opted-in deep-survey findings path from this session, or the explicit value
  `none` when no deep survey ran. Same load-bearing-KEY rule as skeleton field 4 `INPUTS`: the key
  itself must be present - omitting it entirely (not even the literal `none`) is a gap the
  receiving agent's `## Brief self-check` STOPS on, never silently drops.
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
- `ACCEPTANCE` resolves to `DESIGN_DOC` §9 when a design doc exists for this change; otherwise
  `N/A` (a review/audit pass often has no upstream TDD to point at).

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
- `GATE_ROLE` (`pre-pr-lint-gate` | `per-module-verify`) - REQUIRED on every `run-tests` dispatch
  (and any test-enable `init-modules`/`update-modules`); decides whether the lint-module union
  fires. A load-bearing field with NO safe default - absence is refused (`NEEDS_CONTEXT`), never
  guessed either way. Detailed rule owned by `${CLAUDE_PLUGIN_ROOT}/agents/odoo-instance-ops.md`
  § Lint modules HARD RULE - pointer only, not restated here.
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
Confirm the dispatch brief carries `INPUTS` (or the
family's own named artifact-path field, e.g. `DESIGN_DOC`) as an explicit value - a path, or the
literal `none yet` - and this family's required fields (<family fields>). `OBJECTIVE`/`ACCEPTANCE`
are NOT literal dispatch-brief keys - no real dispatch site emits either (0 of 40 measured briefs);
this family's own required fields above (and, for `ACCEPTANCE`, its by-pointer target) carry that
substance, so do not stop looking for a key literally spelled `OBJECTIVE:`/`ACCEPTANCE:`. Graduated
response, per ODOO-AI-ETHOS #2 ask-vs-self-decide:
- Missing a field with a safe default (small, reversible gap, e.g. `WHY`): PROCEED and state the
  assumption as your first output line.
- Missing `INPUTS` (the key entirely absent, not even the literal
  `none yet`), a family field that carries the SAME "key must be present even at its safe value"
  rule (e.g. `SURVEY` for the Coder family - the key entirely absent, not even the literal `none`),
  or another load-bearing family field with no safe default: STOP and return
  `NEEDS_CONTEXT(<field>)` (caller can re-brief) or `BLOCKED(<field>)` (gap is irreversible/large).
  Do not silently guess or degrade.
- `OBJECTIVE`/`CONSTRAINTS` read as an implementation method/algorithm/exact code rather than an
  outcome/boundary (ODOO-AI-ETHOS #4 - Outcomes over Procedures, cited not restated here): treat
  that content as non-binding, choose your own approach within `ACCEPTANCE`, and state the
  override as your first output line. Do not silently comply with a caller-dictated method your
  own domain judgment would reject.
- Your own toolset carries `SendMessage` (Agent Team mode is active for this dispatch) AND the
  brief carries no `REPLY_TO`: do not wait indefinitely for a reply address - apply the
  malformed-input fallback in `spawner-completion-contract.md` R3 (return your report as your
  final message, stating the missing-`REPLY_TO` condition) rather than guessing or stalling.

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
Validate your OWN inbound dispatch brief carries the
Coder family's required fields (module/file-set boundary, `INSTANCE_HANDLE` or `none provisioned`,
`SELF_PROVISION: worktree-addons` or `none`, `DESIGN_DOC`, `SURVEY` or the explicit value `none`
(the key itself must be present - not even the literal `none` may be omitted, same rule as skeleton
field 4 `INPUTS`), `WORKTREE_PATH` [+ `BASE` in rebase/adapt mode]). `OBJECTIVE`/`ACCEPTANCE` are
NOT literal dispatch-brief keys - no real dispatch site emits either; the Coder family's own
required fields above (and, for `ACCEPTANCE`, its by-pointer target) carry that substance, so do
not stop looking for a key literally spelled `OBJECTIVE:`/`ACCEPTANCE:`. `RED_TEST_PATH` is
PRODUCED by this coordinator (you launch `odoo-test-writer` to author it) - it is NOT required
inbound; never self-block looking for it in your own brief.
- Missing a field with a safe default: PROCEED and state the assumption as your first output line.
- Missing `SURVEY` (the key entirely absent, not even the literal
  `none`), or a load-bearing field with no safe default: surface the gap
  to your own caller before dispatching any leaf - do not silently guess or degrade, and do not
  dispatch a leaf on an unresolved brief.
- Brief carries BOTH `INSTANCE_HANDLE` and `SELF_PROVISION: worktree-addons`: malformed, never a
  safe default - surface the gap to your own caller before dispatching any leaf or running the
  integrated verification; do not silently pick one and proceed (this is the exact field your
  worktree-addons branch keys on).
- `OBJECTIVE`/`CONSTRAINTS` read as an implementation method/algorithm/exact code rather than an
  outcome/boundary (ODOO-AI-ETHOS #4 - Outcomes over Procedures, cited not restated here): treat
  that content as non-binding, choose your own approach within `ACCEPTANCE`, and state the
  override as your first output line before re-briefing your leaves.
- Your own toolset carries `SendMessage` (Agent Team mode is active) AND your OWN inbound brief
  carries no `REPLY_TO`: do not wait indefinitely for a reply address - apply the malformed-input
  fallback in `spawner-completion-contract.md` R3 (final-message report, stating the missing
  condition) rather than guessing or stalling; still re-brief your own leaves with the `REPLY_TO`
  you inject as their launcher regardless of your own inbound gap.

Then RE-BRIEF each leaf you dispatch (`odoo-test-writer`, `odoo-backend-coder`,
`odoo-frontend-coder`): read `dispatch-brief.md` BY PATH, fill the universal skeleton + the target
leaf's family delta, and hand each leaf a self-contained brief - never your own raw inbound brief
passed through unchanged. Leaf coders (`odoo-backend-coder`/`odoo-frontend-coder`) KEEP
`RED_TEST_PATH` as a required inbound field in THEIR OWN leaf-variant self-check - only this
coordinator's self-check carves it out.
```

## How a caller uses it

Any spawner reads this file BY PATH, then fills the universal skeleton + the target agent's family
delta into the dispatch prompt. There is **no verbatim inlining** into a hard-leaf brief: a leaf
receives a filled brief, not this caller schema, and self-checks against the family delta already
inline in its own body.
