# Workflow Schema - `workflows/*.workflow.yaml`

> **SSOT for the `*.workflow.yaml` composition contract.**
> The `workflow-chaining` skill reads files conforming to this schema at runtime.
> `docs/reference/workflow-harness.md` §5 references this file for the full field listing.
> Validators: `generator/check_workflows.py` (CI). Tests: `tests/test_workflow_format.py`.

---

## 1. File naming

```
plugins/odoo-ai-agents/workflows/<name>.workflow.yaml
```

- `<name>` must be a valid slug: lowercase, hyphens, no spaces or dots.
- `<name>` must match the `name` field inside the file.
- The `_schema.md` file itself is not a workflow and is ignored by validators.

---

## 2. Top-level fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `name` | string | YES | Slug identifier; must match the filename stem |
| `domain` | enum (9) | YES | Persona bucket - drives `odoo-intake` tier-3 routing row |
| `team_pattern` | enum (6) | YES | Execution shape - tells the runner how to orchestrate phases |
| `description` | string (block) | YES | NL text matched by tier-3 keyword routing and NL-dispatch; no trailing period |
| `output_dir` | string | YES | Must start with `.odoo-ai/` - all artifacts land here |
| `inputs` | string[] | NO | Named args collected by the runner at Phase 0 |
| `phases` | Phase[] | YES | Ordered list of phases; at least 1 required |
| `resume` | bool | NO | Default `false`; if `true`, writes `<slug>-state.json` after each phase |
| `fallback` | string | NO | Degradation policy; `standalone` = each phase runs without OSM |
| `on_complete` | Transition[] | NO | Cross-workflow chain after the final phase (see §11). Runner EMITs matches to its Continuation Contract `next[]`; it never self-dispatches a spawner |

---

## 3. `domain` enum (9 persona buckets)

```
engineering | sales | presales | marketing | strategy | qa | support | content | consultant
```

Matches the 9 README persona buckets. Drives the `odoo-intake` / `odoo-concierge` tier-3 routing
row so this workflow appears in the right routing group without separate registration.

---

## 4. `team_pattern` enum (6 patterns)

| Value | Runner behavior |
|-------|-----------------|
| `Pipeline` | Phases run sequentially; gate between each. Equivalent to the existing command shape. |
| `Fan-out` | A phase with `fanout: true` and `chunk_by` splits input, fires N parallel `context: fork` workers (<=3 concurrent), then aggregates. |
| `Expert-Pool` | `phases[].when:` predicate selects which specialist fires per item. |
| `Producer-Reviewer` | Two phases: `produce` + `review`. Review phase uses `agent:` in read-only mode. |
| `Supervisor` | An `inline` supervisor phase distributes sub-tasks via NL-dispatch and collects results. |
| `Hierarchical` | Top phase decomposes into a generated `phases[]` list bounded to one decomposition level. |

Fan-out ceiling: `context: fork` workers carry the mandatory hard-rules line and are capped at
3 concurrent (Mode A - see `skills/_shared/concurrency-guard.md`, the SSOT for the OOM fan-out rule).

---

## 5. `phases[]` item fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | string | YES | Phase identifier; used in state file, gate messages, and resume logic |
| `skill` | string | ONE OF | Specialist skill name fired by NL-dispatch (must exist in `skills/` or be `inline`/`agent`) |
| `inline` | bool | ONE OF | `true` = runner handles this phase itself; no separate skill dispatched |
| `agent` | string | ONE OF | Agent-tool bundle name for read-only passes (e.g. `odoo-code-reviewer`) |
| `nl_trigger` | string | YES (if skill/agent) | NL prompt written to fire the target skill via description-match dispatch |
| `model_tier` | enum | YES | `haiku` / `sonnet` / `opus` / `inherit`; `sonnet` is the floor for write phases |
| `gate` | string | NO | Gate options shown to user before this phase (e.g. `"yes / edit / cancel"`) |
| `when` | string | NO | Conditional predicate; phase fires only when it evaluates true (otherwise the runner skips the phase). Used by Expert-Pool for per-item specialist selection, and by Pipeline to carry mutually-exclusive conditional branches (e.g. `classification == 'bug'`) |
| `fanout` | bool | NO | Fan-out pattern: split input by `chunk_by` and run parallel workers |
| `chunk_by` | string | NO (with `fanout`) | Field name or expression to split the input for Fan-out |

Exactly one of `skill`, `inline: true`, or `agent` must be present per phase item.

---

## 6. `model_tier` enum

```
haiku | sonnet | opus | inherit
```

- `haiku` - read-only lookup, classification, simple Q&A with no writes. NEVER for write phases or for multi-tool OSM synthesis (e.g. capability tables, feature-existence verdicts); those need `sonnet`.
- `sonnet` - write tasks, edits, single-file refactor, review. **Minimum for write phases.**
- `opus` - cross-file reasoning, orchestration, DAG cluster reasoning. Max 3 concurrent.
- `inherit` - defer to the calling context's model; use for inline phases.

---

## 7. `output_dir` convention

Must start with `.odoo-ai/`. Examples:

```
.odoo-ai/qa
.odoo-ai/discovery
.odoo-ai/upgrade
```

`.odoo-ai/` is gitignored by the `odoo-onboarding` skill. All runtime artifacts are written
here and are never committed to the repo.

---

## 8. Annotated reference example

```yaml
# workflows/discovery-pipeline.workflow.yaml
name: discovery-pipeline
domain: presales
team_pattern: Pipeline
description: |
  Run a two-phase discovery pipeline: summarize raw discovery notes into a structured
  customer profile, then generate a gap analysis effort matrix from that profile.
  Trigger: "discovery to gap analysis", "full presales pipeline", "discovery and scoping
  in one pass", "summarize my notes and scope the project".
output_dir: .odoo-ai/discovery
inputs:
  - discovery_notes

phases:
  - id: summarize
    skill: odoo-discovery-summary
    nl_trigger: >
      Summarize the following raw discovery notes into a structured customer profile
      (industry, headcount, current system, pain points, fit assessment, open questions).
    model_tier: sonnet
    gate: "approve / refine: [feedback] / cancel"

  - id: gap-analysis
    skill: odoo-gap-analysis
    nl_trigger: >
      Using the customer profile produced in the previous phase, generate a full gap
      analysis effort matrix (Standard/Config/Extension/Custom + day estimates) ready
      for a proposal.
    model_tier: sonnet
    gate: "approve / iterate / cancel"

  - id: synthesize
    inline: true
    model_tier: inherit
    gate: "save / discard / cancel"

resume: true
fallback: standalone
```

### Annotation notes

- `team_pattern: Pipeline` - phases run in order with a gate between each; equivalent to
  the existing command shape.
- `inputs: [discovery_notes]` - the runner collects this from the user at Phase 0 before
  emitting the soft-plan-gate.
- `nl_trigger` - the exact NL prompt the runner passes to the context to fire the target
  skill via description-match. It should naturally match the skill's `description` field.
- `inline: true` on `synthesize` - the runner assembles the two phase outputs and writes
  `.odoo-ai/discovery/<slug>-synthesize.md` itself; no external skill is dispatched.
- `resume: true` - the runner writes `.odoo-ai/discovery/<slug>-state.json` after each
  phase so a cancelled or interrupted workflow can be resumed.
- `fallback: standalone` - if OSM is unreachable, each specialist phase runs in standalone
  mode; the runner appends a caveat to the final artifact.

---

## 9. Validation rules (enforced by `generator/check_workflows.py`)

1. All required top-level fields are present.
2. `domain` is one of the 9 allowed values.
3. `team_pattern` is one of the 6 allowed values.
4. `output_dir` starts with `.odoo-ai/`.
5. Each phase has exactly one of `skill`, `inline: true`, or `agent`.
6. For phases with `skill`: the skill name exists as a directory under `plugins/odoo-ai-agents/skills/`.
7. `model_tier` is one of `haiku`, `sonnet`, `opus`, `inherit`.
8. `name` matches the file stem (filename without `.workflow.yaml`).
9. `description` does not end with a period, exclamation mark, or question mark.

---

## 10. Registration

No explicit registration in `plugin.json` is needed. The `workflow-chaining` skill
auto-discovers `*.workflow.yaml` files from the `workflows/` directory at runtime.

---

## 11. `on_complete[]` - cross-workflow transition (optional)

After the final phase, the runner evaluates `on_complete` entries and **emits** matches into
its Continuation Contract `next[]` for the `run-harness` to dispatch (the runner never
self-dispatches a spawner). Each entry:

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `when` | string | YES | Predicate the runner evaluates against accumulated phase outputs - exactly the same mechanism as `phases[].when` (e.g. `classification == 'bug'`). A phase that an `on_complete` reads MUST surface the referenced key in its output (e.g. the qa-suite bug-triage phase emits `code_bugs_found: true`). Simple comparisons only: `==`, `!=` (and `>`/`<` on a numeric key). No formal typed state store - the runner reads the prior phase output and judges, as it already does for `phases[].when` |
| `next` | string | YES | Target skill **or** workflow name; must exist; must not be this same workflow (no self-loop) |
| `reason` | string | YES | Why the chain fires (shown to the human / recorded in the contract) |
| `inputs` | mapping | NO | Args threaded into the next step |
| `gate_tier` | enum | NO | `L0` / `L1` / `L2` - the driver gates accordingly (L2 always human) |

```yaml
on_complete:
  - when: "code_bugs_found == true"        # bug-triage phase must emit this key in its output
    next: odoo-coding
    reason: "qa-suite found code-level bugs; hand to the backend fix bundle"
    inputs: {failing_ref: "${output_dir}/bug-triage.md"}
    gate_tier: L1
```

Validated by `generator/check_workflows.py` (`_validate_on_complete`). Fully optional and
back-compatible: a workflow without `on_complete` behaves exactly as before.
Adding a workflow = dropping a `.workflow.yaml` file; no orchestration code is written.
