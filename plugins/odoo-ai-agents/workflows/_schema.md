# Workflow Schema - `workflows/*.workflow.yaml`

> **SSOT for the `*.workflow.yaml` composition contract.**
> Validators: `generator/check_workflows.py`, `tests/test_workflow_format.py`.

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

WHO the workflow serves; it drives the `odoo-intake` tier-3 routing row. It is not the business
function of the work: that is the per-unit Domain line of
`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`.

---

## 4. `team_pattern` enum (6 patterns)

| Value | Runner behavior |
|-------|-----------------|
| `Pipeline` | Phases run sequentially, without stopping. |
| `Fan-out` | A phase with `fanout: true` and `chunk_by` splits input, fires N parallel `context: fork` workers (<=3 concurrent), then aggregates. |
| `Expert-Pool` | `phases[].when:` predicate selects which specialist fires per item. |
| `Producer-Reviewer` | Two phases: `produce` + `review`. Review phase uses `agent:` in read-only mode. |
| `Supervisor` | An `inline` supervisor phase distributes sub-tasks via NL-dispatch and collects results. |
| `Hierarchical` | Top phase decomposes into a generated `phases[]` list bounded to one decomposition level. |

Fan-out ceiling: `context: fork` workers carry the mandatory hard-rules line and are capped per
`skills/_shared/concurrency-guard.md` Mode A.

---

## 5. `phases[]` item fields

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `id` | string | YES | Phase identifier; used in state file, gate messages, and resume logic |
| `skill` | string | ONE OF | Specialist skill name fired by NL-dispatch (must exist in `skills/` or be `inline`/`agent`) |
| `inline` | bool | ONE OF | `true` = runner handles this phase itself; no separate skill dispatched |
| `agent` | string | ONE OF | Agent bundle name the runner launches for this phase: a read-only pass (e.g. `odoo-code-reviewer`) or a leaf worker (e.g. `odoo-video-producer`) |
| `nl_trigger` | string | YES (if skill/agent) | NL prompt written to fire the target skill via description-match dispatch |
| `model_tier` | enum | YES | `haiku` / `sonnet` / `opus` / `inherit`; a `skill:`/`agent:` phase declares a concrete tier (§6). `inherit` is legal ONLY on an `inline: true` assembler phase (§6) |
| `plan` | bool | NO | `true` on the ONE phase whose output is the workflow plan: the runner runs the phases up to and including it (they write only under the state root, and carry no `gate`), then decides the plan once |
| `gate` | string | NO | A text confirmation before this phase's outward or irreversible action (send, publish, merge, push, delete) - never to advance a phase or save an artifact. Exactly ONE of the two declared reply sets, verbatim, no third set: `"approve / refine: [feedback] / cancel"` (the phase output can be iterated on) or `"approve / skip / cancel"` (do-it-or-skip-it). SSOT: `snippets/planning-gate-contract.md` |
| `when` | string | NO | Conditional predicate; phase fires only when it evaluates true (otherwise the runner skips the phase). Used by Expert-Pool for per-item specialist selection, and by Pipeline to carry mutually-exclusive conditional branches (e.g. `classification == 'bug'`) |
| `fanout` | bool | NO | Fan-out pattern: split input by `chunk_by` and run parallel workers |
| `chunk_by` | string | NO (with `fanout`) | Field name or expression to split the input for Fan-out |

Exactly one of `skill`, `inline: true`, or `agent` must be present per phase item.

---

## 6. `model_tier` enum

```
haiku | sonnet | opus | inherit
```

Choose the tier per `skills/_shared/concurrency-guard.md` § Model-tier selection (the SSOT). A
`skill:`/`agent:` phase declares a concrete tier. `inherit` defers to the calling context's model and
is legal ONLY on an `inline: true` ASSEMBLER phase that merely stitches already-authored prior-phase
outputs.

---

## 7. `output_dir` convention

Must start with `.odoo-ai/`. Examples:

```
.odoo-ai/qa
.odoo-ai/discovery
.odoo-ai/upgrade-plans
```

`workflow-chaining` resolves these relative names against the `$ODOO_AI_HOME` state root at runtime
(`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`).

---

## 8. Reference example

`workflows/discovery-pipeline.workflow.yaml`: a Pipeline of two `skill:` phases followed by an
`inline: true` assembler phase, with `resume: true` and `fallback: standalone`. `nl_trigger` is the
NL prompt the runner passes to fire the target skill via description-match; it should naturally match
the skill's `description`. An `inline` phase writes `<ISOLATE_DIR>/<output_dir minus its .odoo-ai/ prefix>/<slug>-<phase-id>.md`
itself; `resume: true` writes `<ISOLATE_DIR>/<output_dir minus its .odoo-ai/ prefix>/<slug>-state.json` after each phase;
`fallback: standalone` runs each specialist phase without OSM and appends a caveat to the final
artifact. Resolve `<ISOLATE_DIR>` per `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`.

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
10. `model_tier: inherit` is permitted ONLY on an `inline: true` phase; a `skill`/`agent` authoring phase must declare a concrete tier (see §6 for the tier choice).

---

## 10. Registration

No `plugin.json` registration: `workflow-chaining` discovers `*.workflow.yaml` files from `workflows/`.

---

## 11. `on_complete[]` - cross-workflow transition (optional)

After the final phase, the runner evaluates `on_complete` entries and **emits** matches into
its Continuation Contract `next[]` for the plan runner (the main agent) to dispatch (the workflow runner never
self-dispatches a spawner). Each entry:

| Field | Type | Required | Purpose |
|-------|------|----------|---------|
| `when` | string | YES | Predicate the runner evaluates against accumulated phase outputs - exactly the same mechanism as `phases[].when` (e.g. `classification == 'bug'`). A phase that an `on_complete` reads MUST surface the referenced key in its output (e.g. the qa-suite bug-triage phase emits `code_bugs_found: true`). Simple comparisons only: `==`, `!=` (and `>`/`<` on a numeric key). No formal typed state store - the runner reads the prior phase output and judges, as it already does for `phases[].when` |
| `next` | string | YES | Target skill **or** workflow name; must exist; must not be this same workflow (no self-loop) |
| `reason` | string | YES | Why the chain fires (shown to the human / recorded in the contract) |
| `inputs` | mapping | NO | Args threaded into the next step |
| `gate_tier` | enum | NO | `L0` / `L1` / `L2`; recorded metadata only - no runtime step gates on it |

```yaml
on_complete:
  - when: "code_bugs_found == true"        # bug-triage phase must emit this key in its output
    next: odoo-coding
    reason: "qa-suite found code-level bugs; hand to the backend fix bundle"
    inputs: {failing_ref: "${output_dir}/bug-triage.md"}
    gate_tier: L1
```

Validated by `generator/check_workflows.py` (`_validate_on_complete`). Optional.
