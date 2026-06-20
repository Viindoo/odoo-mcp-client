<!-- SSOT snippet. Phase 3.5 of /odoo-forward-port pipeline. Referenced by
     odoo-forward-port skill. Edit here only.
     Cross-ref: fp-intent-4outcome.md, fp-merge-absorption.md, osm-first-contract.md -->

# Forward-Port Symbol Survival Check (Phase 3.5)

**When to run:** after `git merge --no-commit` (Phase 3), before any adapt work (Phase 4).
**Why this phase exists:** git auto-merge silently carries source-side lines that reference
a symbol (field, method, model, view-id, external-id) that was REMOVED or RENAMED in the
target version - no conflict marker appears because the target branch never touched that line.
The result: lint + install may remain green, but the feature breaks at runtime when execution
reaches that line. This is the most common silent correctness failure in forward-port work.
Real example: `account.account.company_id` -> `company_ids` at v18 (PR #14070).

---

## 1. Scope: which files to check

Check BOTH categories - do NOT limit to files with conflict markers:

1. **Files with conflict markers** (`git diff --check` or `grep -r "<<<<<<" .`)
2. **Merge-clean-but-source-touched files** - files modified by the source commits being
   merged but with no conflict marker in the result. To enumerate:

```bash
# compute merge-base first (use the result as <merge-base> below):
# Same-repo (both refs on origin): MB=$(git merge-base <target-branch> <source-ref>)
# Cross-repo: git remote add source <source-repo-clone-url>  # then fetch
#             MB=$(git merge-base <target-branch> source/<branch>)

# commits being merged (adjust range to your actual source..target range)
git log --name-only --format="" ${MB}..<source-ref> | sort -u | grep -v '^$'
```

Cross-reference that list against the clean working tree files. Category 2 is where
autosilent breaks hide - a line was never touched on the target side, so merge has no
information that the referenced symbol has moved.

**INCLUDE `tests/` files in BOTH categories above.** A test file that survives a clean
merge (no conflict marker) is NOT safe-by-default: its `setUpClass`/`setUp`/`_data` setup
or its assertions can reference a core field, model, base-class kwarg, data file, or
external-id that was removed or renamed at the target - and because the merge had no
information that the symbol moved, the test silently lands broken. A broken test crashes at
collection or setup (Phase 5 reads `0 failed, N error(s)` = the tests never ran), so it must
be triaged HERE, alongside production code, not waved through as "just a test". Do not filter
`tests/`, `*/tests/`, or `test_*.py` out of the scope list.

---

## 2. Grounding every symbol via odoo-semantic-mcp

For each file in scope, extract every Odoo symbol the merged code references:
fields (`record.<field>`), methods (`Model._<method>`), model names (string literals in
`_inherit`/`comodel_name`/domain), view `ref()` / `xml_id`, `ir.model.fields` names,
manifest `depends` entries, and ORM chain segments.

For **each symbol** call odoo-semantic-mcp against the **target version** to confirm
existence + correct type. The `odoo_version` parameter is MANDATORY on every call:

```
model_inspect(model='account.account', method='summary', odoo_version='18.0')
entity_lookup(kind='field', model='account.account', field='company_ids', odoo_version='18.0')
api_version_diff(symbol='account.account.company_id', from_version='17.0', to_version='18.0')
check_module_exists(name='sale_management', odoo_version='18.0')  # manifest depends entries (module rename/split)
```

A symbol that OSM does not return for the target version is ABSENT at the target unless
disk-fallback (local source read) confirms it in a customer-local module. Absence = broken
reference = blocker, not a warning.

---

## 2.5. Symbol classes that auto-merge silently (no conflict marker each)

Section 2 grounds the symbols you can SEE in a diff. This section enumerates six symbol
classes that survive a clean merge with NO conflict marker AND are easy to miss with a
naive field/method scan - each can pass lint + install green yet crash at collection,
load, or runtime on the target. Run EVERY check below over the scope list from Section 1
(production AND `tests/` files). Each check states: what auto-merges silently, the command
to enumerate candidates, and how to ground each candidate against the target. Any candidate
that fails its ground is a SYMBOL-BROKEN finding (Section 4) - resolve via the
[[fp-intent-4outcome]] bucket before Phase 4 adapt.

### (a) Test base-class signature drift

**Autosilent:** a source test's `setUpClass(cls, ...)` / `setUp(self, ...)` (or a `super()`
call) passes a kwarg that the target's base class (`AccountTestInvoicingCommon`,
`TransactionCase`, `SavepointCase`, `HttpCase`, a localization base, ...) NO LONGER accepts at
the target version. The merge keeps the source call verbatim; collection then crashes with
`TypeError: setUpClass() got an unexpected keyword argument` - the whole test class never runs.

**Enumerate:** for every test class in a touched test file, record its base class(es) and the
kwargs it passes into `setUpClass`/`setUp`/`super().setUpClass(...)`:

```bash
grep -nE "class .*\((Transaction|Savepoint|Http|.*Common|.*Case)" <test-files>
grep -nE "def (setUpClass|setUp)\(|super\(\)\.(setUpClass|setUp)\(" <test-files>
```

**Ground:** resolve the base-class signature AT THE TARGET and compare it to what the source
test passes. List the candidate base classes, then inspect each:

```
test_base_classes(odoo_version='18.0')
test_class_inspect(name='AccountTestInvoicingCommon', odoo_version='18.0', module='account')
```

Compare the target `setUpClass`/`setUp` signature to the source call site. A kwarg present in
the source call but ABSENT from the target signature = BROKEN (bucket b: drop/rename the kwarg
to the target equivalent, or bucket c: re-derive the setup per the target idiom).

### (b) File-existence references

**Autosilent:** merged code opens or reads a data file (`open(<path>)`,
`tools.file_open(<path>)`, `get_module_path(<mod>) + '/<f>'`, `get_resource_path(...)`, a CSV /
XML / JSON data asset) that was DELETED or relocated at the target. The merge is clean (the
path string was never touched on the target side); at runtime the read raises
`FileNotFoundError`.

**Enumerate:**

```bash
grep -nE "file_open|get_module_path|get_resource_path|open\(" <files>
```

**Ground:** confirm the target file exists. Use the target checkout directly, or confirm the
data file is still declared by the owning module at the target:

```bash
test -f <target-tree>/<module>/<path-to-data-file>   # exit 0 = present
```

```
module_inspect(name='l10n_vn', method='summary', odoo_version='18.0')  # confirm data file still declared in manifest
```

A path with no file on the target checkout AND not declared by the module's manifest =
BROKEN (bucket b: point at the target's replacement asset; bucket c: re-create the asset; or
bucket d: skip + document if the consuming feature is gone).

### (c) Dynamic ref / xml_id construction

**Autosilent:** an external-id is built at runtime - `ref('%s.%s' % (mod, xid))`,
`env.ref(f"{module}.{name}")`, `self.ref('mod.' + var)` - so the xml_id never appears as a
static string and a literal grep for the id finds nothing. The merge keeps the construction
verbatim; if the resolved external-id was removed/renamed at the target, `env.ref(...)` raises
`ValueError: External ID not found`. An `noupdate="1"` record makes the loss permanent (an
update run will not re-create it).

**Enumerate** every `ref(` / `env.ref(` / `self.ref(` whose argument is NOT a plain string
literal (f-string, `%`-format, or `+`-concatenation):

```bash
grep -nE "\.?ref\(\s*[f'\"]?%|\.?ref\([^'\"]*\+|f['\"]" <files>
```

**Ground:** reconstruct each candidate external-id from the surrounding variables, then confirm
it resolves at the target. For a view xml_id use `entity_lookup` (kind='view' requires
`xmlid=`), or grep the target data XML for the `id=`:

```
entity_lookup(kind='view', xmlid='account.view_move_form', odoo_version='18.0')
```

```bash
grep -rn 'id="view_move_form"' <target-tree>/account/   # data-side confirm for non-view records
```

An external-id that does not resolve at the target = BROKEN (bucket b: update to the target's
id; bucket c: re-create the record; bucket d: skip if the feature is gone). Flag
`noupdate="1"` records explicitly - the loss is not self-healing.

### (d) Python import-statement survival

**Autosilent:** a source `from odoo.addons.<mod>.<path> import X` (or a relative
`from ..models.x import Y`) survives the clean merge even though `<mod>`, `<path>`, or `X` was
DELETED or relocated at the target. There is no conflict marker; the module raises `ImportError`
at load time, which aborts the whole module install/upgrade.

**Enumerate + ground:** after the merge, for every touched `.py`, compile it and run a static
undefined-name pass, then confirm cross-module imports resolve at the target:

```bash
python -m py_compile <files>          # syntax-level survival
pyflakes <files>                      # undefined-name from a failed relative import surfaces as F821
```

```
module_inspect(name='account_accountant', method='summary', odoo_version='18.0')  # confirm the imported symbol's owning module still exists at target
```

An import whose target symbol/module is gone = BROKEN (bucket b: repoint to the target module;
bucket c: re-implement the imported helper; bucket d: skip if the dependency is gone).

### (e) Import-survival AST scan (pyflakes over every clean-merged source-touched .py)

**Autosilent:** beyond the explicit import check in (d), a merge can leave any `.py` with a
broken name binding (a symbol used after its definition was removed upstream, a re-export that
vanished, a name shadowed away). These do not produce conflict markers and lint configs often
tolerate them.

**Enumerate + ground:** run `pyflakes` over EVERY clean-merged source-touched `.py` from the
Section 1 list (not only the conflict-marked ones):

```bash
pyflakes <every-clean-merged-source-touched-.py>
```

Treat every F-code on a source-touched file as a finding to TRIAGE, not a style nit:
`F821` (undefined name) = a removed/renamed symbol survived the merge - almost always BROKEN;
`F811` (redefinition) = a merge stacked two definitions of the same name - confirm which one
wins; `F401` (unused import) on a source-touched file = a symbol the merged code stopped using,
or an import that should have been adapted - confirm it is intentional, not a half-applied
rename. Ground the suspected symbol against the target with `model_inspect` / `entity_lookup` /
`module_inspect` (`odoo_version=` mandatory) before deciding the bucket.

### (f) installable flag transition (A9)

**Autosilent:** a `__manifest__.py` carried in the merge delta flips `installable` between the
source and the target end-state (`True` -> `False` or `False` -> `True`). This silently changes
which modules Phase 5 actually loads and tests - a module that flips to `installable: False`
drops out of the install set with no error, so its forward-ported code is never exercised
(linked to A3 - the `Loading module X` parse). The merge has no conflict because only one side
touched the flag.

**Enumerate** every manifest in the merge delta and check the flag on each side:

```bash
git diff <merge-base>..<source-ref> -- '*/__manifest__.py' | grep -nE "installable"
# then read the TARGET end-state flag per manifest to detect the flip:
grep -nE "installable" <target-tree>/<module>/__manifest__.py
```

**Ground + record:** confirm the post-merge end-state of `installable` for each affected module
and record it. A flip is not auto-broken, but it MUST be a recorded finding (Section 4,
kind=installable-flag) because it determines whether the forward-ported code in that module is
actually loaded and verified in Phase 5 - an un-noticed `True` -> `False` flip is a silent drop
of the whole module from the verify set.

---

## 3. When a symbol is absent or changed at the target

**NEVER leave the auto-merged line unchanged.** Force the intent into one of the
4-outcome buckets defined in [[fp-intent-4outcome]]:

| Situation | Bucket |
|---|---|
| Replacement exists at target (renamed/restructured) | (b) adapt - rewrite reference to new symbol |
| Behavior must be re-implemented; mechanism gone | (c) re-implement per target idiom |
| Feature was a workaround for a limitation the target no longer has | (d) skip + document |
| Target core already handles this natively | (a) core covers it - remove code |

The rule: the adapt diff (in the merge commit per [[fp-merge-absorption]]) MUST reflect
the bucket decision. An auto-merged reference to a dead symbol is merge-commit debt that
will surface as a runtime exception; resolve it here, not later.

---

## 4. Output contract

Produce a symbol-survival finding list before proceeding to Phase 4. Each entry uses the
`kind=` discriminator so the finding is unambiguous and machine-greppable. For a field /
method / model / view-ref / xml_id symbol from Section 2:

```
SYMBOL-BROKEN | kind=field|method|model|view-ref|xml_id | <symbol> | <file>:<line>
               | target-replacement: <replacement or NONE> | bucket: <a|b|c|d>
               | evidence: <OSM call + result summary>
```

For a test / file / import / installable finding from Section 2.5, use the same line shape
with the matching `kind=` value and a `<detail>` field:

```
SYMBOL-BROKEN | kind=test-base-class | <Class>.setUpClass kwarg <kwarg> absent at target
               | <file>:<line> | bucket: <b|c> | evidence: test_class_inspect(...) signature diff
SYMBOL-BROKEN | kind=file-path | <path> deleted at target | <file>:<line>
               | bucket: <b|c|d> | evidence: test -f miss + module_inspect manifest check
SYMBOL-BROKEN | kind=import | <from ... import X> target symbol gone | <file>:<line>
               | bucket: <b|c|d> | evidence: pyflakes F821 + module_inspect(...)
SYMBOL-BROKEN | kind=installable-flag | <module> installable <old> -> <new> at end-state
               | <manifest>:<line> | bucket: record | evidence: git diff + target manifest flag
```

An empty list is a valid (and desirable) result - document it as
`SYMBOL-SURVIVAL: clean (0 broken references found)`.

A non-empty list is a BLOCKER for Phase 4 adapt start on those files - resolve each
entry (apply the bucket action) before the adapt subagent touches those files. An
`installable-flag` entry is a recorded finding (not a Phase-4 blocker by itself) but MUST be
carried into Phase 5 so the verify set reflects the real install set.

---

## Why not defer this to Phase 5 verify-by-behavior

Phase 5 runs the test suite and catches failures where a test exercises the broken path.
Symbol-survival catches broken references in code paths with **no test coverage** - runtime-rare
paths, configuration-only code, XML view references, and `ir.model.fields` lookups that
never appear in any test fixture. It also catches breaks that PREVENT Phase 5 from running at
all: a test base-class kwarg drift (2.5a) or a broken import (2.5d) crashes collection, so Phase
5 reports `0 failed, N error(s)` - the tests never ran, and a naive reading of the counts looks
green. Principle #3 of the forward-port design ("no-conflict but feature dies") mandates
grounding at the SYMBOL level here, not only at the behavior level in Phase 5. Both gates are
required; neither replaces the other.
