# Frontend-fidelity verify-gate examples (issue #37 acceptance proof)

Two fixtures that demonstrate `scripts/verify-frontend.sh` (the post-write gate added in
issue #37). They are acceptance-test fixtures, not production code.

Run from the plugin root:

```bash
bash scripts/verify-frontend.sh skills/odoo-frontend-coding/examples/good/greeting_widget.js \
                                 skills/odoo-frontend-coding/examples/good/greeting_widget.xml
bash scripts/verify-frontend.sh skills/odoo-frontend-coding/examples/broken/broken_widget.xml \
                                 skills/odoo-frontend-coding/examples/broken/broken_styles.scss
bash scripts/verify-frontend.sh skills/odoo-frontend-coding/examples/broken/class1_handlers.xml
```

## `good/` - passes the gate

A clean OWL 2.x component (Odoo v16-v18):
- `useService("ui")` wrapped in `useState` (class-2 reactivity preserved)
- handlers are auto-bound (`t-on-click="onIncrement"`) or explicit-`this` arrows, including the
  params-before-arrow form `(ev) => this.onIncrement(ev)` - all core-valid
- a `contenteditable` CSS **selector string** in JS (`querySelector("[contenteditable=true]")`)
  is legit and does NOT block - class-3 only applies to `.xml`/`.html` templates
- no raw `contenteditable` attribute, no hardcoded palette, no `--bs-*`

Observed result: **PASS (exit 0)**, 0 BLOCK. The only WARN is the graceful-degradation notice
when `prettier` is not installed locally (the JS format check soft-warns instead of hard-failing,
and Tier-2 still resolves the committed config at `<odoo>/addons/web/tooling/_eslintrc.json`).

## `broken/` - caught by the gate

A deliberately-broken sample exercising the BLOCK and WARN classes:
- `broken_widget.xml`: class 1 (bare free-identifier arrow `() => onSave()`), class 3 (raw
  `contenteditable`), class 6 (`t-set-slot="body"` under `<Dialog>`) - all **BLOCK**
- `broken_styles.scss`: class 4 (`calc(map-get(...))` without `#{}`), class 5 (`var(--bs-primary)`) - **WARN**

Observed result: **FAILED (exit 1)** - 3 BLOCK + 2 WARN. The gate stops the change.

`class1_handlers.xml` exercises the broadened class-1 catches:
- `(ev) => onSave(ev)` (params before the arrow), `() => OnSave()` (PascalCase),
  `() => _onSave()` (leading underscore) - all bare free-identifiers, all **BLOCK** (3 BLOCK).

These forms slipped through the original empty-parens / lowercase-only class-1 rule.

## Precision guarantee

The class-1 rule does NOT flag the core-valid forms `t-on-click="onFoo"` (auto-bound),
`() => this.onFoo()` (explicit `this`), nor the params-before-arrow `(ev) => this.onFoo(ev)`;
only the bare free-identifier arrow form blocks.
See the full corrected catalogue at `../../_shared/odoo-frontend-fidelity.md`
(section "OWL pitfall catalogue").

> Note: the Tier-2 static checks are grep-based and also scan comments, so a docstring that
> literally contains a flagged pattern (e.g. `useService("ui")`) may produce a WARN. This is a
> known limitation of the WARN tier - it never blocks.
