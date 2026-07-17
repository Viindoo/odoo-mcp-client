# Resource-teardown behavioral evals

Purpose: behavioral evals proving the resource-teardown contract
(`plugins/odoo-ai-agents/snippets/resource-teardown-contract.md`, T0-T4 + the
CLOSE(browser)-vs-RELEASE/DROP(instance) verb glossary) actually changes an EXECUTING agent's
behavior, not just its wording. A static wording-freeze guard
(`tests/test_resource_teardown_contract.py`) can prove the contract's text is unchanged; it
cannot prove an agent reading it actually closes the right things and releases/drops the right
things at runtime. That is what the two evals here are for:

- **Eval A - verb collision** (`eval-a-verb-collision/`): proves the CLOSE(browser)-vs-
  RELEASE(instance) verb split (T2 vs T3) holds even when an agent's brief carries a FORWARDED
  instance lease plus a hard "never release it" ban right next to a "close every page you
  opened" instruction. Targets `odoo-user-doc-writer` and `odoo-marketing-writer`.
- **Eval B - visual-regression matrix** (`eval-b-visual-regression-matrix/`): proves the
  visual-regression matrix-close (T0/T2) leaves no page the run created still open after a
  5-screen x 4-breakpoint x 2-state sweep. Targets `odoo-visual-regression`.

This directory lives outside `plugins/*/skills/` deliberately - an eval workspace under
`plugins/*/skills/` breaks `make gen` (the SSOT generator only expects `SKILL.md` + its own
generated regions under a skill directory).

## What's here

- **`lib/grading.py`** - the two DETERMINISTIC graders (`grade_eval_a`, `grade_eval_b`; no LLM
  judgment - both PASS assertions are mechanical: tool-name suffix match, substring/regex
  absence, page-id set membership). Imported directly by
  `tests/test_resource_teardown_evals.py`, which runs in CI today with no live model or browser
  required - it grades hand-authored fixture transcripts to prove the grading logic itself is
  correct (and can fail for the right reason).
- **`eval-a-verb-collision/*.evals.json`** and **`eval-b-visual-regression-matrix/*.evals.json`**
  - the RUNNABLE eval definitions (skill-creator `evals/evals.json` schema) for exercising the
  REAL agent/skill against a live model + browser MCP. These are NOT auto-run in CI - they
  require dispatching a real subagent (Eval A) or invoking a real inline skill session against a
  live Odoo instance (Eval B) and capturing its transcript. Each file's `how_to_run_live` field
  gives the exact command:

  ```
  python3 evals/resource-teardown/lib/grading.py <eval-a|eval-b> <transcript.jsonl>
  ```

  Exit code 0 = PASS, 1 = FAIL; stdout is a `grading.json`-shaped report (pass/fail per
  expectation + evidence).

## Where the rules come from

The contract these evals check is the single source of truth:
`plugins/odoo-ai-agents/snippets/resource-teardown-contract.md` (T0 DONE-gate, T1 ownership
matrix, T2 browser CLOSE rules, T3 instance RELEASE rules, T4 failure/handoff paths). Do not
duplicate contract wording here - if a PASS assertion and the contract ever disagree, the
contract is the source that changes, and these evals get updated to match it.
