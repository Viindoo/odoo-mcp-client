# Front-door boundary evals

Purpose: prove that a FRONT-DOOR SKILL, at runtime, DISPATCHES the specialist call its phase text
assigns to a delegate instead of running it in its own context. A static prose guard can prove the
dispatch wording is present; only grading a transcript can prove an orchestrator reading it
actually dispatched.

## What is executable, and what is not - read this before trusting a green build

- **`lib/grading.py` IS executed in CI.** `tests/test_frontdoor_boundary_evals.py` imports
  `grade_frontdoor_boundary` and runs it over HAND-AUTHORED fixture transcripts: the
  pre-correction shape must be FLAGGED, the corrected shape must PASS, and a leaf specialist
  issuing the same calls must never be flagged. That test runs under `make test` and in
  `.github/workflows/validate.yml` with no live model required.
- **The `*.evals.json` files are NOT executed by any runner in this repo.** There is no
  `claude plugin eval` target in the `Makefile` and none in `.github/workflows/`. Nothing runs
  these definitions on a PR. Treat them as (a) the machine-readable SSOT of what each front door
  may not do in its own context - `forbidden_tool_classes` is consumed by both `lib/grading.py`
  and the CI fixture test, so the two cannot drift apart - and (b) a runnable definition for a
  MANUAL live run.

So "the grader is wired" means "the grading logic is unit-tested against fixtures". It does NOT
mean "front doors are graded against live transcripts in CI". Do not report a green CI run as
evidence that a front door respected its dispatch boundary in a real session.

## Running one live (manual)

Each `*.evals.json` carries a `how_to_run_live` field with the exact steps. In outline: drive the
real skill to the phase under test, capture the MAIN-context transcript to `transcript.jsonl`,
then:

```
python3 evals/frontdoor-boundary/lib/grading.py evals/frontdoor-boundary/<skill>.evals.json <transcript.jsonl>
```

Exit code 0 = PASS, 1 = FAIL; stdout is a `grading.json`-shaped report. Read each file's `scope`
field first - the forbidden classes are scoped to a phase SEGMENT, and grading a whole run will
surface earlier phases that are licensed on purpose.

## Where the rules come from

The skill body is the source of truth: `plugins/odoo-ai-agents/skills/<skill>/SKILL.md` and its
`references/`. Do not duplicate phase wording here - when a PASS assertion and the skill ever
disagree, the skill is what changes, and these definitions get updated to match it.

This directory lives outside `plugins/*/skills/` deliberately - an eval workspace under
`plugins/*/skills/` breaks `make gen`.
