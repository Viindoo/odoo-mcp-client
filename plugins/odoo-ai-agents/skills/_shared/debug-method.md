# Scientific Debugging Method - cross-layer SSOT for all Odoo debugging

> Shared methodology doc for the debug front-door (`odoo-debug`) and its specialist agents
> (`odoo-backend-debugger`, `odoo-ui-debugger`) and, by light reference, the reactive mode of the
> audit skills (`odoo-security-audit`, `odoo-perf-audit`, `odoo-deprecation-audit`). It exists so
> every debug run - whatever the layer - follows the SAME industry-standard scientific loop and
> emits the SAME evidence-bearing contract, instead of jumping to a guessed fix. Skills/agents
> cross-reference this doc; they do not duplicate it.
>
> **You are an AI agent executing a debug task.** This doc is written FOR you, the execute-time
> reader. The Output Contract at the bottom is not optional decoration - filling every field is
> how you prove (to yourself and the caller) that you actually performed each step. An empty or
> hand-waved field means that step was skipped, which means the root cause is not yet proven.

---

## Root-cause-first rule (non-negotiable)

**DO NOT PROPOSE A FIX BEFORE THE ROOT CAUSE IS PROVEN.** Fixing a symptom you do not understand
creates whack-a-mole: each wrong fix makes the next bug harder to find. If intent is unclear,
widen the search (upstream callers, downstream consumers, the README/spec/original commit) before
acting. If still unclear, stop and ask - do not guess.

A fix is only valid when you can state three things: (a) the symptom, (b) the root cause that
produces it, (c) why this fix blocks that cause rather than masking the symptom.

---

## The loop (apply in order; do not skip)

1. **Reproduce - stably.** A bug you cannot reproduce you cannot debug. Find the smallest input /
   state / click-path that triggers it ~100% of the time. This is the most important step;
   skipping it is the root of every "fix bừa" (blind fix). Record the exact recipe.

2. **Observe - do not guess.** Read the FULL traceback bottom-up (the last line is the real
   exception; the lines above are the call stack that led there). For UI, read the browser console
   + network, not the server log. Do not assume a variable's value - make it observable
   (log / print / `evaluate_script` / inspect a record). Ground every structural claim about Odoo
   source in OSM (`set_active_version` then `model_inspect` / `resolve_orm_chain` /
   `find_override_point` / `lookup_core_api` / `resolve_stylesheet`), never from memory.

3. **Hypothesize - falsifiably.** State a specific, refutable cause: "X is None because the
   `@api.depends` omits field Y, so the compute never re-runs." A hypothesis you cannot prove
   wrong is useless (mirror of the test rule: a test that cannot fail protects nothing).

4. **Bisect - halve the search space.** The fault lies between "data still correct here" and
   "data already wrong here." Put an observation point in the middle; each check halves what
   remains. Use `git bisect` for a regression over time; binary-search the call stack / data flow
   for a logic fault.

5. **Change ONE variable at a time.** If you change several things and the symptom clears, you do
   not know which one mattered - and you have likely introduced a second bug.

6. **Confirm by toggle.** If your root cause is correct you can make the bug APPEAR and DISAPPEAR
   at will (toggle the suspected cause on/off). If you cannot, you have not found the root cause -
   return to step 3. This is the gate between "plausible" and "proven."

   **MED-6 - `0 failed, N error(s)` is NOT a pass.** When a test run reports errors (not failures)
   originating from setUpClass / setUp / module-load, the test bodies DID NOT RUN - the
   collection or fixture crashed before any assertion could execute. Do NOT read this as green.
   Do NOT conclude "transient/flaky" unless you have a deterministic RED->GREEN toggle you have
   ACTUALLY EXECUTED. Require `0 errors` before reading the failed/passed counts; fix
   setup/collection errors first.

7. **Lock it with a regression test.** Write a test that protects the BEHAVIOR (the business rule
   /contract), not the current code. It must be RED before the fix (proving it catches the bug)
   and GREEN after. Never weaken an assertion or skip a case to get green.

---

## Handoff, not self-fix

These debug agents DIAGNOSE; they do not edit source. Once the root cause is proven and the fix
location named, hand off to `odoo-coding` (it writes both the Python/XML and the JS/OWL/SCSS
fix) for the edit, and to the relevant audit skill when a broader scan is warranted.

---

## Output Contract (MANDATORY - every debug run fills ALL fields)

Emit this block. A field you cannot fill truthfully marks an incomplete diagnosis - say so
explicitly (e.g. `Confirm-by-toggle: NOT YET CONFIRMED - hypothesis unproven`) rather than
leaving it blank or fabricating. This contract is the soft enforcement of the loop above: an
honest fill is only possible if you actually performed each step.

```
## Debug: <symptom> · layer=<backend|ui|perf|security|install> · Odoo v<N>

Reproduction: <smallest stable recipe that triggers it, + observed frequency>
Observation: <full traceback bottom line / console+network / record state - the raw evidence>
Hypothesis (falsifiable): <specific refutable cause>
Evidence + bisect: <how the search space was halved; OSM/code evidence localizing the cause>
Confirm-by-toggle: <how toggling the cause made the bug appear/disappear - or NOT YET CONFIRMED>
Root cause: <the single proven cause - NOT a symptom>
Fix location: <file · method/selector · which coding skill to hand off to>
Regression test (red->green): <test that protects the behavior; assert it fails pre-fix>
Confidence: <HIGH ONLY if the toggle was actually EXECUTED + observed (and any regression test actually run RED) and the cause is OSM-grounded; a described-but-unexecuted toggle/test or an inferred location caps at MEDIUM; LOW if unproven>
Grounding: <osm | local-source (not OSM-indexed) | OSM unavailable - ungrounded>
```
