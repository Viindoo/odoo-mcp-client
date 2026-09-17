# Runbot Parity Checklist

SSOT for the full-suite gate that Runbot runs when a module flips `installable: False -> True`.
Used in: the P5 install + test gate (upgrade pipeline) and as a pre-PR checklist (WS6 P15).

> **Trigger:** any module in the cluster has `installable` flipped `False → True` in this PR.
> When this checklist is triggered, EVERY item below must pass before the PR is considered ready.
> Items with a version annotation apply only for the listed Odoo series.

---

## Gate 1 - flake8 (all series)

Run flake8 **without** the `flake8-bugbear` plugin. Runbot does NOT have bugbear installed;
running WITH it produces false B950/B018 failures. The tell: `B018` firing on a manifest string
is a bugbear false positive - means bugbear is present and must be uninstalled from the venv.

```bash
# Check whether bugbear is present - if so, uninstall before running
pip show flake8-bugbear 2>/dev/null && pip uninstall -y flake8-bugbear

# Run flake8 on installable modules only (same scope Runbot uses)
flake8 --select=E,W,F,C,B,B9 \
       --max-line-length=120 \
       <module_dirs...>
```

Reproduce count must match the Runbot build for the branch. If the count differs, check for
stray bugbear or a different `--max-line-length` value.

---

## Gate 2 - Odoo lint test module

Reproduce the backend code-quality CI by running the lint-class modules. Resolve WHICH modules the
gate is made of for this series - and confirm each one really installed - per
`${CLAUDE_PLUGIN_ROOT}/snippets/lint-gate-modules.md`, then append one `/<module>` tag per resolved
module to `--test-tags` on a `-u <module> --test-enable` instance run. Requires a running
instance + DB.

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true

# One /<tag> per lint module the snippet above resolved as present on this profile,
# each also present in the -u install list for this build.
odoo-bin -d <DB> -u <module> --test-enable \
    --test-tags '/<module>,/<lint module>[,/<lint module>...]' --stop-after-init \
    --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

See `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md` for the authoritative gate reference.
Memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

---

## Gate 3 - manifest description (RST format, v12+)

The `description` key in `__manifest__.py` must be valid RST (reStructuredText). Runbot runs
`docutils.core.publish_string` over it; invalid RST fails the lint gate silently in some series
but loudly in others.

```bash
python -c "
import docutils.core, ast, sys
for f in sys.argv[1:]:
    m = ast.literal_eval(open(f).read())
    if m.get('description'):
        docutils.core.publish_string(m['description'], writer_name='html')
" <module_dirs...>/*/__manifest__.py
```

---

## Gate 4 - module images (PIL-open check)

Runbot verifies that `static/description/icon.png` (and any image in `static/description/`)
can be opened by Pillow without error. A corrupt or 0-byte image fails the gate.

```bash
python -c "
from PIL import Image
import glob, sys
for f in glob.glob('<module_dir>/static/description/**/*', recursive=True):
    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg')): continue  # SVG ok
    try: Image.open(f).verify()
    except Exception as e: print(f'FAIL {f}: {e}'); sys.exit(1)
"
```

---

## Gate 5 - .po file format

Each `.po` file under `i18n/` must:

1. Contain a `#. module: <technical_name>` comment for every message. Missing comments cause
   `translate.py` to crash at import time (Runbot mis-blames the NEXT module in the load order).
2. Use `%s` / `%(name)s` placeholders (not `{name}` Python 3 style) for messages that will be
   translated by `ir.translation`.

```bash
# Check for missing module comments
for po in <module_dir>/i18n/*.po; do
    python -m msgfmt --check-format "$po" 2>&1
    grep -L '^#\. module:' "$po" && echo "MISSING module comment: $po"
done
```

---

## Gate 6 - same-module-name rule

The technical name (directory name) of each module must be unique across the entire install set.
A duplicate causes the second module to shadow the first silently.

Pass the ADDONS-PATH ENTRIES themselves (the dirs on `--addons-path`), never a repo root: a
descriptor sits at `<addons_path>/<module>/`, so it is exactly **depth 2** below each start point.
`-maxdepth 2` is both necessary and sufficient - a shallower scan matches nothing and reports
"no duplicates" without examining a single module, while a deeper scan reaches nested packaging
trees that Odoo never loads (it treats only an entry's IMMEDIATE children as modules) and invents
duplicates that are not in the install set.

```bash
# Check for duplicates across the combined addons path
find <addons_path1> <addons_path2> ... -maxdepth 2 \( -name __manifest__.py -o -name __openerp__.py \) \
    | xargs -I{} dirname {} | sort -u | xargs -I{} basename {} | sort | uniq -d
# `sort -u` collapses per DIRECTORY before the names are counted: a module carrying BOTH descriptor
# names yields two find hits for one module, which uniq -d would otherwise report as a duplicate of
# itself. That module is a defect in its own right - see the note below - but it is not THIS gate's.
# Both descriptor names: this gate applies from v8, where the descriptor is __openerp__.py -
# globbing __manifest__.py alone reports "no duplicates" on v8/v9 without checking anything
# Any output = duplicate technical names = FAIL

# Locate every reported name so the FAIL is actionable (uniq -d prints names, not paths)
find <addons_path1> <addons_path2> ... -maxdepth 2 \( -name __manifest__.py -o -name __openerp__.py \) \
    | grep -E "/(<name1>|<name2>)/[^/]+$"
```

> **A module holding BOTH `__manifest__.py` and `__openerp__.py` is itself a FAIL.** Odoo loads
> `__manifest__.py` and ignores `__openerp__.py` unconditionally, so on a v8.0/v9.0 module the stray
> `__manifest__.py` becomes the descriptor and every model, view, and dependency the real
> `__openerp__.py` declares is dropped - with no error. Delete the wrong-era descriptor
> (`__openerp__.py` from v10.0+, `__manifest__.py` from v8.0-v9.0) before re-running this gate:
>
> ```bash
> find <addons_path1> <addons_path2> ... -maxdepth 2 -name __manifest__.py \
>     | xargs -I{} dirname {} | xargs -I{} sh -c 'test -f "$1/__openerp__.py" && echo "BOTH: $1"' _ {}
> ```

---

## Gate 7 - full untagged suite (installable-flip trigger)

When a module flips `installable: False -> True`, the full gate suite (Gates 1-6) runs on Runbot
with `--init <module>`. Reproduce Runbot's DEMO SHAPE FOR THIS SERIES, and take it from RUNBOT's own
configuration for that series - this gate's whole purpose is parity, so deriving its shape from this
plugin's tables instead would make the gate agree with us rather than with CI. Where Runbot's config
is not to hand, fall back to the automation-test row of
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build PURPOSE and say in the
report that the demo shape was assumed, not confirmed:

> **This gate is DELIBERATELY untagged** - exemption case 4 of
> `${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md` (reproducing a CI gate that itself runs
> untagged). Parity with Runbot is the point, so the scope must match Runbot's, not the change's
> blast radius. Declare it as `TEST_TAGS: full` when dispatching through `odoo-instance`, so the log
> shows a full run that was intended rather than a tag someone forgot. Every OTHER test run in this
> checklist carries `--test-tags`.

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true

# No demo flag either way: on the series where demo defaults ON the test build simply
# inherits it, and on the series where it defaults OFF the test environment does not
# accept demo data at all. Never add the enable-flag to a --test-enable build.
odoo-bin -i <module> --test-enable --stop-after-init <db-options> \
         --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

Memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

> The `-i` here reproduces the Runbot FRESH-init scenario (module just flipped installable, clean
> DB). Re-running this gate against a DB where the module is ALREADY installed uses `-u <module>`
> instead - `-i` on an installed module is a no-op. Confirm the flags via `cli_help`; see
> `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.

Additionally run `base.TestInvisibleField` and (for `hr.*` modules) `hr.TestSelfAccessProfile`:

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true
odoo-bin --test-tags base.TestInvisibleField,hr.TestSelfAccessProfile \
         -i <module> --stop-after-init <db-options> \
         --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

See `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` (CLI demo flag section) for the
exact flag semantics per version. See `${CLAUDE_PLUGIN_ROOT}/snippets/upg-conventions.md` for
Viindoo-specific gates (hr.employee groups, always-invisible comment).

---

## Version-keyed applicability summary

| Gate | v8-v12 | v13-v14 | v15-v16 | v17 | v18+ |
|---|---|---|---|---|---|
| flake8 (no bugbear) | yes | yes | yes | yes | yes |
| /test_lint (Odoo CE) | yes (v14+) | yes | yes | yes | yes |
| Viindoo lint module (presence AND name per series - `lint-gate-modules.md`) | no | no | resolve | resolve | resolve |
| description RST | yes (v12+) | yes | yes | yes | yes |
| images PIL | yes | yes | yes | yes | yes |
| .po `#. module:` | yes | yes | yes | yes | yes |
| same-module-name | yes | yes | yes | yes | yes |
| TestInvisibleField | no | no | no | no | v18+ |
| TestSelfAccessProfile | no | no | no | v17+ | yes |
