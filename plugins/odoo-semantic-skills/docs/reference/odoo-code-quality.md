# Odoo code-quality gate — local reproduction (multi-version aware)

> **What this is.** A local, pre-push **parity** gate for the Odoo CI code-quality checks, so the
> `odoo-coding` / `odoo-code-review` / `odoo-qa-suite` / `odoo-deploy-checklist` / `wave` personas
> catch lint failures **before** push — not in CI. Not a CI replacement; a fast inner-loop mirror.
>
> Consumed by: `agents/odoo-coder.md`, `agents/odoo-code-reviewer.md`,
> `skills/odoo-deploy-checklist`, and the test-run SSOT `ODOO-TESTING.md`. Brand-fidelity is a
> sibling check (Section 5).

## The gate is two public parts

1. **Core `test_lint`** — Odoo core's own lint test module (manifest checks, eslint, pofile,
   `__init__` consistency, …). It runs **only** when included in `--test-tags`; a normal
   `--test-tags /<module>` run does **not** include it. → see `ODOO-TESTING.md`.
2. **`pylint-odoo`** — the OCA pylint plugin (`consider-merging-classes-inherited`, `sql-injection`,
   `print-used`, `translation-*`, …). Not a test-suite module; reproduced by
   **`scripts/verify-backend.sh`** (the backend sibling of `verify-frontend.sh`).

A plain `odoo-bin --test-enable --test-tags '/<module>'` run includes **neither**, and OSM
`lint_check` is a fuzzy V0 screen that does not reproduce pylint-odoo (it can miss SQL injection).
That gap is exactly why lint failures slipped to CI.

## `verify-backend.sh` — the inner-loop static gate

```
scripts/verify-backend.sh [--series X.Y] [file ...]          # default target: git diff --name-only HEAD (.py only)
scripts/verify-backend.sh --provision [--series X.Y]         # opt-in: build the pinned isolated tools venv
```

Contract (same shape as `verify-frontend.sh`): env overrides, graceful degradation (soft-warn,
exit 0, when the toolchain is absent), HARD-fail (exit 1) only on real findings, default target
`git diff --name-only`. Series is resolved from `--series` / `$ODOO_SERIES` / `.odoo-ai/context.md`
(`odoo_version`).

It runs `pylint --load-plugins=pylint_odoo` from an **isolated tools venv**
(`$ODOO_AI_DIR/tools/pylint-<series>/`) — never the instance venv — with the
pylint/astroid/pylint-odoo versions pinned per Odoo series.

## Per-version matrix (`scripts/lib/odoo-python-matrix.json` → `lint`)

`pylint-odoo` major tracks the Odoo series; **pylint/astroid must be era-matched** to that major
(16/17 → pylint 2.15, 18 → pylint 3.x, 19 → pylint 4.x, which `pylint-odoo 10` hard-requires) —
using an off-era `pylint` crashes the Odoo-era checker plugins.

| Odoo series | pylint-odoo | pylint | astroid | lint Python | note |
|---|---|---|---|---|---|
| 8.0 – 15.0 | `>=8,<9` | `>=2.15,<2.16` | `>=2.13,<2.14` | 3.10 | best-effort (pre-modern) |
| 16.0 / 17.0 | `==8.0.22` | `==2.15.10` | `==2.13.5` | 3.10 | **verified-faithful** |
| 18.0 | `>=9,<10` | `>=3,<4` | `>=3,<4` | 3.12 | |
| 19.0 | `>=10,<11` | `>=4,<5` | `>=4,<5` | 3.12 | `pylint-odoo 10` requires `pylint 4` |

`lint_python` is the venv interpreter the **linter** needs (e.g. pylint 2.15 requires ≤ 3.11) — it
is independent of the instance's `recommended` Python. When **v20** ships, default to extending the
19.0 row; only add a new row if the era-matched pylint/astroid majors must change.

## The vanilla trap (why we never run bare pylint)

A source pragma `# pylint: disable=consider-merging-classes-inherited` (R8180) is **valid and
required** when `pylint_odoo` is loaded. Run the same file through **bare** pylint (plugin not
loaded) and that pragma reads as `unknown-option-value (W0012)` — which `--disable=all` does **not**
reliably suppress — so it looks like a failure to "fix" by deleting the pragma. Deleting it then
**re-breaks real CI**. Therefore `verify-backend.sh` **always** loads `pylint_odoo` and never runs
bare core pylint.

Verified behaviour (Odoo 17.0, pylint-odoo 8.0.22):
- pragma **present** + plugin loaded → suppressed cleanly, **no W0012** (PASS).
- pragma **absent** in module context → R8180 **flagged** (BLOCK).
- a `cr.execute("… '%s'" % x)` → `E8103 sql-injection` **flagged** (BLOCK); OSM `lint_check`
  returns `0 violations` for the same input.

## Enabled-code set — single source of truth from the deployment

When a deployment ships its own quality module (commonly `test_pylint` / `test_lint`) on the addons
path, `verify-backend.sh` **derives the enabled-code set from it** (its `.pylintrc` or an
`ENABLED_CODES` list) rather than vendoring any deployment-internal config into this public plugin.
Resolution order: `$ODOO_PYLINTRC` → deployment quality module → repo-root `pylintrc` → shipped
fallback `scripts/odoo-pylintrc` (OCA defaults). **No deployment-internal data lives in the plugin.**

## Copy-paste reproduce

```bash
# one-time: provision the pinned, isolated tools venv for the series
scripts/verify-backend.sh --provision --series 17.0

# fast inner loop (no DB): pylint-odoo on changed Python
scripts/verify-backend.sh                      # changed files vs HEAD
scripts/verify-backend.sh path/to/models.py    # explicit

# authoritative loop (with DB): include the lint test module in the suite
odoo-bin -d <DB> -u <module> --test-enable \
  --test-tags '/<module>,/test_lint' --stop-after-init --log-level=test
# + the deployment's quality module tag when present, e.g. ,/test_pylint
```

## ESLint / Prettier are NOT version-pinned here

Frontend JS formatting is governed by the **target repo's committed** `.eslintrc*` +
`package.json`/`package-lock.json` (e.g. `eslint 8` + `prettier 2.7`). `verify-frontend.sh` already
resolves this (repo config → Odoo `addons/web/tooling` → shipped fallback → soft-warn). No version
matrix is needed for them.

## Section 5 — Brand fidelity (sibling, optional, brand-agnostic)

Brand-token fidelity is a separate optional layer and is **not** vendored: the plugin ships a
mechanism, the consumer declares the brand. Set `brand_tokens_source` in `.odoo-ai/context.md` to a
JSON map (`{"--primary": "#1E88E5", …}`). Two halves share `scripts/lib/color_delta.py` (stdlib
CIEDE2000): the **static** half (`verify-frontend.sh` Tier 4) WARNs on hardcoded SCSS hex within ΔE
of a brand token; the **runtime** half (`odoo-ui-review` Step 4b) ΔE-diffs `getComputedStyle(:root)`
against the declared map. WARN-tier (ΔE rounding makes false-blocks easy). Full rationale:
`skills/_shared/odoo-frontend-fidelity.md` Section G. Mirrors this gate's "derive from the consumer
environment, vendor nothing" principle.

## Scope / non-goals

- Local **pre-push parity**, not a CI replacement.
- No deployment-internal config vendored in this public plugin (enabled codes + brand tokens are
  read from the consumer environment).
- OSM `lint_check` upgrade (real per-version linter / server-fed pin matrix) is **server-side**
  follow-up work, tracked separately — out of scope for this client repo.
