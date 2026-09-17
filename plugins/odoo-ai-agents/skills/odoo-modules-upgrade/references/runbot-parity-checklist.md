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
with `--init <module>`. Its demo shape is the automation-test row of
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build PURPOSE, which is the
RECORDED Runbot shape for each series - and it is also the only shape this gate can actually run,
because `odoo-instance` REFUSES `DEMO: on` on a `--test-enable` build wherever demo defaults off.
So do not go looking for a different answer to pass to the dispatch. If you have Runbot's own config
for the target series and it DISAGREES with that row, that is a FINDING to report - the row is
stale and needs correcting at its source - never a reason to request demo on this build:

> **This gate is DELIBERATELY untagged** - exemption case 4 of
> `${CLAUDE_PLUGIN_ROOT}/snippets/test-scope-contract.md` (reproducing a CI gate that itself runs
> untagged). Parity with Runbot is the point, so the scope must match Runbot's, not the change's
> blast radius. Declare it as `TEST_TAGS: full` when dispatching through `odoo-instance`, so the log
> shows a full run that was intended rather than a tag someone forgot. Every OTHER test run in this
> checklist carries `--test-tags`. Like every `--test-enable` dispatch, this one also states
> `GATE_ROLE` - `node-verify` unless this run IS the run's one designated pre-PR lint gate - because
> `odoo-instance` refuses a test-run dispatch that leaves it unresolved rather than picking one.

```bash
[ -z "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" ] || [ "${ODOO_AI_LIMIT_MEMORY_HARD-4294967296}" = "0" ] || ulimit -Sv "$(( ${ODOO_AI_LIMIT_MEMORY_HARD-4294967296} / 1024 ))" 2>/dev/null || true

# No demo flag either way: on the series where demo defaults ON the test build simply
# inherits it, and on the series where it defaults OFF the test environment does not
# accept demo data at all. Never add the enable-flag to a --test-enable build.
odoo-bin -i <module> --test-enable --stop-after-init <db-options> \
         --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

Memory-cap policy: `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-bin-resource-limits.md`.

**Gate 7b - demo-load check, on any series where the suite above ran demo-less.** An
installable-flip is the first time the module's own `demo/` data is ever loaded, so a suite that
ran without demo has proved nothing about it, and broken demo XML would ship unnoticed - while
`${CLAUDE_PLUGIN_ROOT}/snippets/demo-data-dynamic.md` requires the module to ship that data. Prove
it in a SECOND, SEPARATE build that loads demo and runs NO tests. Never merge the two: demo rows in
a DB the suite asserts on make a correct record-counting test fail, and the tempting repair is to
weaken the test rather than to remove the demo rows that never belonged there.

```bash
# Install only - NO --test-enable anywhere on this line.
# The enable-flag exists ONLY on the series where demo defaults off - which is exactly the series
# where this gate fires, so the two conditions coincide. Resolve the spelling from the pivots demo
# rows for the target series, never by copying this line onto an earlier one.
odoo-bin -i <module> --with-demo --stop-after-init <db-options> \
         --limit-memory-hard=${ODOO_AI_LIMIT_MEMORY_HARD:-4294967296}
```

Dispatch it through `odoo-instance` as `OPERATION: init`, `DEMO: on`, no `TEST_TAGS` and no
`GATE_ROLE` - that field is required only for a build whose purpose is running tests, which this one
is not, so supplying it here would misdescribe the build. Without `--test-enable` no suite runs at
all, tags or none, so the untagged-run hazard the scope contract warns about cannot arise here. The
demo-load row of `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` § Demo data by build
PURPOSE is what authorises `DEMO: on` here, and it authorises it ONLY because this build runs no
tests.

**Check the manifest FIRST - this gate cannot see demo that was deleted.** Odoo's demo loader
returns success immediately when the manifest declares no `demo`/`demo_xml` key: nothing is loaded,
nothing is logged, the install is green. So a rewrite that DROPPED the key during the upgrade passes
this gate silently, which is the likeliest demo regression of all. Before running the build, compare
the target manifest against the source one: if the module declared demo at source and no longer
does, FAIL here and report it - do not let the build's own verdict answer a question it is
structurally unable to answer.

**Verdict, once the build runs.** Dispatched through `odoo-instance`, a demo load that raises is
already caught for you: the loader logs it with a traceback, and the runner's install-failure
matcher (`${CLAUDE_PLUGIN_ROOT}/scripts/setup-steps/55-instance-ops.sh`, `_INSTALL_FAIL_RE`) turns
any traceback into `STATUS=error`. Take that as the verdict. The caveat matters only if you ever run
`odoo-bin` by hand outside that runner: Odoo catches every exception from a module's demo load,
downgrades it to a WARNING, finishes installing the module WITHOUT its demo data, and still exits 0
(`odoo/modules/loading.py`, `load_demo`) - so a hand-run gate that reads the exit code alone reports
PASS on precisely the breakage it exists to catch. There, read the log for the demo-failure warning
instead, taking its wording from that build's own `load_demo`.

> **Gate 7b is FRESH-DB ONLY - never re-run it with `-u`.** On the upgrade path Odoo does not consult
> the demo enable-flag at all: it reloads demo only when the module's stored `demo` flag is already
> set (`odoo/modules/loading.py`, the `else: # 'upgrade' or 'reinit'` branch). A module that Gate 7
> installed demo-less therefore has that flag FALSE, so `-u <module>` plus the enable-flag loads
> nothing, the build goes green, and this gate reports PASS having verified nothing. Always give it
> its own clean database.
>
> (The `-i`/`-u` note that follows applies to GATE 7, above, not to Gate 7b: `-i` there reproduces
> the Runbot FRESH-init scenario, and re-running Gate 7 against a DB where the module is ALREADY
> installed uses `-u <module>` instead - `-i` on an installed module is a no-op.) Confirm the flags via `cli_help`; see
> `${CLAUDE_PLUGIN_ROOT}/docs/reference/ODOO-TESTING.md`.

Do NOT add a `--test-tags` line naming individual framework-validation classes here. This gate is
already UNTAGGED, so every installed module's suite runs - the `base` and `hr` framework classes
included. Naming them would add no coverage at all, and would add a name that has to be re-checked
against every series forever.

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
| Framework-validation classes (which ones exist per series - `odoo-version-pivots.md`) | resolve | resolve | resolve | resolve | resolve |
| Gate 7b demo-load (install only) | only where Gate 7 ran demo-less | same | same | same | same |

