# Runbot Parity Checklist

SSOT for the full-suite gate that Runbot runs when a module flips `installable: False → True`.
Used in: P5 demo=on gate (upgrade pipeline) and as a pre-PR checklist (WS6 P15).

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

## Gate 2 - Odoo lint test module (/test_lint + /test_pylint v16+)

Reproduce the backend code-quality CI by running Odoo's own lint test module. Append `/test_lint`
to `--test-tags` on a `-u <module> --test-enable` instance run (v14+; renamed from `test_pylint`
at v13). On v16+ Viindoo profiles also include `/test_pylint` (tvtmaaddons). Requires a running
instance + DB.

```bash
# v14-v15 CE (and v16+ CE without Viindoo tvtmaaddons):
odoo-bin -d <DB> -u <module> --test-enable \
    --test-tags '/<module>,/test_lint' --stop-after-init

# v16+ Viindoo (tvtmaaddons installed):
odoo-bin -d <DB> -u <module> --test-enable \
    --test-tags '/<module>,/test_lint,/test_pylint' --stop-after-init
```

See `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md` for the authoritative gate reference.

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

```bash
# Check for duplicates across the combined addons path
find <addons_path1> <addons_path2> ... -maxdepth 1 -name __manifest__.py \
    | xargs -I{} dirname {} | xargs -I{} basename {} | sort | uniq -d
# Any output = duplicate technical names = FAIL
```

---

## Gate 7 - full-suite demo=on (installable-flip trigger, version-keyed)

When a module flips `installable: False → True`, the full `test_pylint` suite (Gates 1-6) runs
on Runbot with `--init <module>` and **demo data ON** (the default for all v8-v18; explicit
`--with-demo` for v19+). Run locally with demo ON to reproduce:

```bash
# v8-v18: demo ON is the default - no extra flag
odoo-bin -i <module> --test-enable --stop-after-init <db-options>

# v19+: demo ON requires explicit flag
odoo-bin -i <module> --with-demo --test-enable --stop-after-init <db-options>
```

Additionally run `base.TestInvisibleField` and (for `hr.*` modules) `hr.TestSelfAccessProfile`:

```bash
odoo-bin --test-tags base.TestInvisibleField,hr.TestSelfAccessProfile \
         -i <module> --stop-after-init <db-options>
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
| /test_pylint (tvtmaaddons) | no | no | v16+ | yes | yes |
| description RST | yes (v12+) | yes | yes | yes | yes |
| images PIL | yes | yes | yes | yes | yes |
| .po `#. module:` | yes | yes | yes | yes | yes |
| same-module-name | yes | yes | yes | yes | yes |
| TestInvisibleField | no | no | no | no | v18+ |
| TestSelfAccessProfile | no | no | no | v17+ | yes |
