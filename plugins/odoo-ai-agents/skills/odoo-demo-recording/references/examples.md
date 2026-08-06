# Demo Recording Examples

## Example 1 - sales order demo MP4

Prompt: "Record a 30-second demo of creating and confirming a sales order in Odoo 17."

- Round 0: context → `odoo_version: <version>`, base URL, login; format MP4, ~30s.
- Round 1 (parallel): `check_module_exists(name='sale_management', odoo_version='<version>')` + `module_inspect(name='sale', method='views', odoo_version='<version>')` + `model_inspect(model='sale.order', method='summary', odoo_version='<version>')` + `find_examples(query='create confirm sale order flow', odoo_version='<version>')` → step list.
- Round 2: log in, navigate to Sales, set clean state.
- Round 3: record click path: New → pick customer → add line → Confirm; `stop_recording`, then
  `close_page` the driven page before Round 4.
- Round 4: mint the slug once (`sale-order-20260803-a1b2`, per
  `${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 1), then save to
  the Tier-2 ISOLATE dir resolved per
  `${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md` -
  `<ISOLATE_DIR>/visual/videos/sale-order-20260803-a1b2.mp4`, report path + duration.

## Example 2 - website portal GIF, recorder unavailable

Prompt: "Make a GIF of the customer portal invoice download."

- Round 1: `module_inspect` for portal views; `find_examples(query='portal invoice download flow', odoo_version='<version>')`.
- Round 3: recorder unavailable → capture `take_screenshot` frames at each step; no `stop_recording`
  needed (none started), but still `close_page` the driven page before Round 4.
- Round 4: assemble frames into a GIF; prefix output with the recorder-unreachable warning.

## Example 3 - narrated before/after bug-evidence pair (chrome-devtools only)

Prompt: "Record narrated before/after evidence that the LCL ocean line doesn't carry the chosen
co-loader as vendor - fix is already merged - `--label before`, then `--label after`."

- Trigger: request states "narrated before/after evidence" and supplies `--label` → Narrated
  evidence mode (see `SKILL.md` § Narrated evidence mode).
- Round 0: resolve context as usual; additionally collect `LABEL=before` (first run) /
  `LABEL=after` (second run), `VERDICT_STATUS=bug` / `fixed`, `VERDICT_EXPECTED='vendor shows the
  chosen co-loader'`, `VERDICT_OBSERVED='vendor field is empty'` (before) / `'vendor shows the
  chosen co-loader'` (after). `COMMIT_SHA` not supplied by the caller → resolve inline with
  `git rev-parse --short HEAD` in the repo under demonstration. Mint the pair's slug ONCE, shared by
  both runs: `lcl-coloader-vendor-20260803-a1b2` (per `visual-evidence-lifecycle-contract.md`
  Clause 1 - a bare date alone would collide with any other same-day recording of a
  similarly-named feature).
- Round 1: unchanged - `module_inspect` / `model_inspect` / `find_examples` for the freight sale
  order flow, producing the step list (open order → add LCL ocean line → pick co-loader → save).
- Round 2: only chrome-devtools is reachable this run (playwright not wired) → first
  `navigate_page` passes the overlay bundle (`references/narrated-mode.md`) as `initScript`;
  follow with `evaluate_script` setting the badge - `__setBadge('before', '<sha>')` (red) for the
  `before` run, `__setBadge('after', '<sha>')` (green) for the `after` run.
- Round 3: per step - `evaluate_script` sets the caption (e.g. `__setCaption('Pick co-loader X as
  vendor on the LCL ocean line')`), THEN perform the click/fill, THEN `take_screenshot` (frame
  shows the RENDERED result - for the `before` run this is the empty vendor field, verified
  against the captured frame per the Grounding rule, not assumed); finish with
  `evaluate_script` calling `__endCard('bug', <expected>, <observed>)` (before run) /
  `__endCard('fixed', <expected>, <observed>)` (after run), held for the final 2+ frames, then
  `close_page` (chrome-devtools has no recorder to stop - pagecast is excluded here, see § Overlay
  mechanism).
- Round 4: no frame-to-clip assembler configured in this deployment → the ordered PNG sequence is
  the deliverable for each label; report `status: DONE` with a `concerns:` entry naming the
  missing assembler, with
  paths `<ISOLATE_DIR>/visual/videos/lcl-coloader-vendor-20260803-a1b2-before/` and
  `.../lcl-coloader-vendor-20260803-a1b2-after/` (frame sequences, same minted slug from Round 0,
  `-before`/`-after` suffix - the random suffix is what keeps this pair from colliding with any
  other same-day `lcl-coloader-vendor` recording).
