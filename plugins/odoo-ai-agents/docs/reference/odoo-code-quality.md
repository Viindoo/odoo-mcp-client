# Odoo code-quality gate - local reproduction (multi-version aware)

> **What this is.** A local, pre-push gate for the Odoo CI code-quality checks, so the
> `odoo-coding` / `odoo-code-review` / `odoo-qa-suite` / `odoo-deploy-checklist` / `run-harness` personas
> catch lint failures **before** push - not in CI. Not a CI replacement; a fast inner-loop mirror.
>
> Consumed by: `agents/odoo-backend-coder.md`, `agents/odoo-frontend-coder.md`,
> `agents/odoo-code-reviewer.md`, `skills/odoo-deploy-checklist`, and the test-run SSOT
> `ODOO-TESTING.md`. Brand-fidelity is a sibling check (Section 4).

## Backend lint - Odoo's lint test module (SSOT: ODOO-TESTING.md)

The backend lint gate is Odoo's own `test_lint` module (v14+) plus the Viindoo `tvtmaaddons`
custom `test_pylint` module (v16+). **Full description, version table, and invocation command:
`docs/reference/ODOO-TESTING.md` § "Quality gate / lint tests".**

Append `/test_lint` (and `/test_pylint` for v16+ Viindoo) to `--test-tags` in any `odoo-bin` test
invocation. Requires a running instance + DB. **Tagging alone is not enough** - the lint module(s)
must also be INSTALLED in the target DB or the tag silently selects nothing (false-clean pass); see
`ODOO-TESTING.md` § "Install the lint modules (not just tag them)".

> A plain `odoo-bin --test-enable --test-tags '/<module>'` run includes **neither** lint module.
> OSM's `lint_check` (V0.5 hybrid matcher) does not reproduce the full Odoo AST checker set: it
> fires deterministically on security-rule patterns like sql-injection (labeled `[pattern]`) but
> is a hint, not the full gate.

## JS lint gate - repo-pinned eslint oracle

Frontend JS is linted by `verify-frontend.sh` Tier 1 using the **repo-pinned** eslint toolchain,
not a global binary. Resolution order: the changed-files repo's `node_modules/.bin/eslint` ->
main worktree `node_modules/.bin/eslint` (git-worktree-aware) -> `npx --no-install`. The gate
runs `eslint --no-eslintrc -c <_eslintrc.json> --resolve-plugins-relative-to <MAIN_ROOT>` - the
same oracle Runbot uses. Version pinning is provided by the repo's own `node_modules`; no
separate matrix is needed here.

The gate is tri-state:

| Result | Exit | Meaning |
|---|---|---|
| `RESULT: PASS (clean)` / `RESULT: PASS (with N warning(s))` | 0 | eslint ran on the repo-pinned toolchain and found zero errors |
| `RESULT: FAIL (N blocking issue(s) - fix before proceeding)` | 1 | eslint found >=1 error |
| `RESULT: CANNOT-VERIFY (did NOT run: <gate list> - DO NOT treat as pass)` | 2 | eslint did NOT run - the parenthetical names which gate(s) and the `[CANNOT-VERIFY]` line above names why |

Exit 2 is **not clean**. An agent MUST NOT declare done on `CANNOT-VERIFY`; it must clear the
stated cause or escalate. Only exit 0 with `RESULT: PASS` counts as a green JS lint gate.

**Read the cause, do not assume it.** `CANNOT-VERIFY` has several causes and they need different
remedies: an unresolved toolchain (run `npm install` in the target repo), a prettier version-pin
mismatch, a series whose checkout ships no JS gate - and an **unresolved target series**, where the
toolchain is fine and nothing needs installing.

**Target series resolution.** The `_eslintrc.json` is series-specific, so the gate must know which
series the sources are written against. It resolves that from `ODOO_SERIES` or from
`scripts/lib/odoo_series.py`, the repo's series-derivation SSOT, which resolves only from evidence
that IS the series (the core's own `release.py`; a series-named branch). An addon's
`__manifest__.py` `version` deliberately resolves **nothing**: it is the addon's own version, so
`0.3.1` is not series `0.3`, and even a series-prefixed value survives a code-level upgrade
unbumped. When nothing declares a series, the remedy the gate prints is the whole fix -
`ODOO_SERIES=<series> verify-frontend.sh ...`.

**Every run prints a gate ledger** in the Summary - one row per tier, `RAN` / `DID NOT RUN` /
`n/a` / `not configured` - whatever the verdict. Read it before quoting any tier's clean line: a
tier that skipped itself prints nothing, while the tiers that did run still print their clean
lines, so "no issues" in isolation is not evidence that the gate ran.

## Section 4 - Brand fidelity (sibling, optional, brand-agnostic)

Brand-token fidelity is a separate optional layer and is **not** vendored: the plugin ships a
mechanism, the consumer declares the brand. Place a JSON map (`{"--primary": "#1E88E5", …}`) at
`<SHARE_DIR>/brand-tokens.json` (resolve `<SHARE_DIR>`/`<ISOLATE_DIR>` once per
`${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md`; substitute the captured absolute path -
never write the placeholder or a bare `.odoo-ai/` into a Read/Write/Edit) to opt in; its absence
skips the check silently. Two halves share `scripts/lib/color_delta.py` (stdlib
CIEDE2000): the **static** half (`verify-frontend.sh` Tier 4) WARNs on hardcoded SCSS hex within ΔE
of a brand token; the **runtime** half (`odoo-ui-review` Step 4b) ΔE-diffs `getComputedStyle(:root)`
against the declared map. WARN-tier (ΔE rounding makes false-blocks easy). Full rationale:
`skills/_shared/odoo-frontend-fidelity.md` Section G. Mirrors this gate's "derive from the consumer
environment, vendor nothing" principle.

## Scope / non-goals

- Local **pre-push parity**, not a CI replacement.
- No deployment-internal config vendored in this public plugin (enabled codes + brand tokens are
  read from the consumer environment).
- OSM `lint_check` got a server-side hybrid-matcher upgrade (V0.5: deterministic `[pattern]`
  on security-rule classes). The remaining upgrade (a real per-version linter / server-fed
  pin matrix reproducing the full Odoo AST checker set) is still **server-side** follow-up work,
  tracked separately - out of scope for this client repo.
