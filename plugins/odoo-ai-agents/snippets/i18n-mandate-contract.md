<!-- SSOT snippet. The single home for the MANDATORY i18n reconcile step its callers share:
     the mandate wording, the caller obligations, the enumerated escapes, the decidable trigger,
     and the orchestrator's must-not-instruct list (what a CALLER may never tell the i18n leaf,
     each row pointing at the SSOT that owns the fact). Edit here only;
     consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/i18n-mandate-contract.md.
     The i18n PROTOCOL itself (export, load, diff-review, adjudicate) is owned by
     ${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md and is NOT restated here. -->

# i18n mandate contract (SSOT)

Across a major Odoo series the `.pot`/`.po` TOOLING changes independently of content: the v19
`odoo-bin i18n` subcommand family replaces the v8-v18 `--i18n-export` / `--load-language` flags, and
`ir.translation` disappears between v15 and v16. A module carried across that boundary needs its
catalog re-exported and reconciled through the TARGET series' path once, whether or not its own strings
changed. A content predicate ("did the diff touch a label?") is therefore the wrong shape for this
gate, and it under-fires silently.

## The mandate

Dispatch the `odoo-i18n` skill ONCE per surviving unit. This is NOT opt-in. The run is not DONE until
`odoo-i18n` returns a per-module result or a RECORDED escape from the table below.

**Caller obligations (all five, or the mandate is unsound):**
1. Pass `WORKTREE_PATH` - the worktree the adapt wrote. `.po`/`.pot` are git-tracked and
   `odoo-translator` is a separate agent context that does not inherit cwd.
2. Pass an `INSTANCE_HANDLE` (or `SELF_PROVISION: worktree-addons`) whose addons path covers that
   worktree, so the export reads POST-ADAPT code
   (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage assertion). An
   instance on the principal checkout makes a worktree-only `msgid` surface as nothing and the loss is
   committed unseen.
3. Pass explicit `TARGET LANGUAGES` whenever you already have one - never withhold a resolvable list.
   When you genuinely have none (nothing configured, nothing inferable on your side), OMIT the field
   rather than fabricate one: `odoo-i18n` P0 still runs its OWN tiers 2-4 (machine-global registry,
   `.po`-filename inference, live `res.lang` query) against whatever IS available, and only records
   escape E3 once ALL of tiers 1-4 come up empty. `odoo-i18n` has no hardcoded target-language
   default to fall back on - omitting the field never triggers one, inside a mandate or outside
   it; it only ever reaches escape E3 above.
4. Present the returned result at YOUR OWN existing human gate - do NOT let `odoo-i18n` open a separate
   STOP per invocation. A mandated step that always stops is a deadlock.
5. Hand over an instance BUILT FOR EXPORT - installed WITH DEMO DATA, `en_US` plus the target
   languages active - or hand over none and let `odoo-i18n` build its own
   (`SELF_PROVISION: worktree-addons`). Reusing a lease you happen to hold (a test DB, a review
   instance, anything `demo=off`) truncates the catalog: demo-owned records carry translatable terms,
   and re-exporting a maintained `.po` from a demo-less build drops entries the committed file
   already holds, which then read as accidental losses. Demo loads at `-i` only, so it cannot be
   added afterwards. The wrong instance is worse than none - none BLOCKS loudly, the wrong one
   succeeds quietly. Rule + per-series flags:
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-i18n/references/i18n-recipe.md` KT4/KT5.

## Escape hatches (ENUMERATED - no others; every skip RECORDED, never silent)

| # | condition (mechanical) | record verbatim | status |
|---|---|---|---|
| E1 | the unit's verdict is DELETE-absorbed or OBSOLETE | `i18n: n/a (module deleted)` | proceed |
| E2 | the module ships no `i18n/` directory (§ Catalog-presence check) AND the trigger table below fires ZERO signals - decidable in BOTH flows | `i18n: n/a (no catalog, no translatable delta)` | proceed |
| E3 | tiers 1-4 of language resolution all empty (caller passed none and `odoo-i18n` itself could infer none) | `i18n: not-applicable (no target language resolvable from tiers 1-4)` | proceed |
| E4 | forward-port only: `installable_false == yes` for this module (the lint-only lane) | `i18n: n/a (installable:False at target - lint-only lane)` | proceed |
| E5 | no instance can be provisioned | `i18n: blocked (no instance)` | **BLOCKED** |
| E6 | the instance's addons path does not cover `WORKTREE_PATH` | `i18n: blocked (instance addons-path excludes the worktree)` | **BLOCKED** |
| E7 | the handed-over instance was built without demo data (obligation 5) | `i18n: blocked (export instance has no demo data - catalog would be truncated)` | **BLOCKED** |

Anything not in this table is NOT an escape. "The diff looked label-free" is E2, which requires
BOTH conditions.

## Orchestrator obligations - what a CALLER must never instruct

A caller need not know how translation works, but it must not instruct AGAINST it: a leaf told one
thing by its contract and another by its brief follows the brief. These four are the instructions
that actually get given. Each row names the SSOT that owns the fact; none is restated here.

| Never instruct | Why it is wrong | Owner of the fact |
|---|---|---|
| "skip demo / reuse the test DB / build it fast" | Demo-owned records carry translatable terms, so a demo-less build ships a truncated catalog AND turns committed entries into phantom removals | `skills/odoo-i18n/references/i18n-recipe.md` KT4 |
| "get the untranslated count to zero" | Odoo stores a translation equal to its source EMPTY, so many blanks are REVIEWED do-not-localise decisions; a zero-blank target orders the leaf to overwrite them | `snippets/po-entry-semantics.md` § The identity rule |
| "export just the `.pot`" / a fresh instance per language | Every artifact of one run must come from ONE build, or the reconcile compares different term inventories and its rulings are void | `skills/odoo-i18n/references/i18n-recipe.md` KT5 |
| "test that the translation is right / the catalog complete" | That wording is improved continuously, so the test fails on an improvement; the catalog is gated by this pipeline, never by the suite | `snippets/test-behavior-contract.md` § Never assert TRANSLATED or DISPLAY text |

Positive form, short enough to carry: **dispatch `odoo-i18n`, give it a worktree plus either a
demo-loaded instance or permission to build one, name the languages if you know them, and let it
decide what counts as translated.**

## Catalog-presence check (E2 clause 1 - mechanical, decidable by BOTH flows)

"Ships an `i18n/` directory" is decided the SAME way regardless of which pipeline is asking - defined
ONCE here; neither caller restates it.

- **What is read:** whether `<module>/i18n/` exists AND holds at least one `*.po` or `*.pot` file. An
  absent directory and a present-but-empty directory both count as "no catalog."
- **Which tree:** `WORKTREE_PATH` - the SAME worktree caller obligation 1 already requires, at its
  current on-disk state (this run's adapt has already landed there).
- **Which ref:** none - a plain FILESYSTEM read of the worktree as it stands, never a git-history read
  and never Odoo Semantic MCP. OSM does NOT index `i18n/*.po`/`*.pot` (`module_inspect`,
  `describe_module`, `check_module_exists` return no such listing) - disk read is the only path.
- **The two outcomes:**
  - `<module>/i18n/` exists and holds >=1 `.po`/`.pot` file -> catalog PRESENT -> E2 clause 1 FAILS
    (this module already ships a catalog; the mandate applies regardless of the trigger table).
  - Directory absent, or present but holding zero `.po`/`.pot` files -> catalog ABSENT -> E2 clause 1
    SATISFIED - evaluate clause 2 (the trigger table below).

Mechanical form (either flow runs this identically, via `git-toolkit:git-ops`, read-only):

```bash
test -d "<WORKTREE_PATH>/<module>/i18n" && \
  find "<WORKTREE_PATH>/<module>/i18n" -maxdepth 1 \( -name '*.po' -o -name '*.pot' \) | grep -q .
```

Exit 0 -> catalog PRESENT. Non-zero (dir absent, or the `find`/`grep` pipe empty) -> catalog ABSENT.

## Condition 2 - forward-port's already-upgraded test (decidable, no new probe)

Read `installable_false` from the module's row in `merge-log.md` - the verbatim `merge_log_line` the
prober emitted, coerced to `yes`/`no`. `installable_false == no` -> the module is live at the target and
the mandate applies. `== yes` -> E4. Categories 1-2 the orchestrator resolved itself without a probe:
read the same `yes`/`no` it recorded. Neither present -> **BLOCK**; do not guess and do not re-probe.
`installable_false` is the ONE field this condition reads - do not substitute any other field name
(internal-only, prober-side values are never persisted and no consumer parses them by name).

## Trigger table - "touches translatable terms" (E2 clause 2 / condition 1 - BOTH flows)

Scan the diff THIS RUN's own adapt produced for the module - never the module's whole history, only
what this run changed. The scan target resolves per caller (same signal table, different source):

- **forward-port:** the ALREADY-MATERIALIZED per-commit dumps for this batch -
  `<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump` (full patch: message + diff).
- **modules-upgrade:** the module's own P4 adapt diff - invoke `git-toolkit:git-ops` (read-only) for
  a full-patch diff of `<module>/` between `<work-base>` and `HEAD`, inside the module's worktree
  (`<path>/upg-<module>` when a child worktree was used, else `<path>/upg-integration` under the
  collapse-first `n<=1` rule). No new dump file is needed; this reuses the SAME worktree + base already tracked for
  the module's own commit.
- **run-harness:** the run-integration branch's aggregate diff (every module, across every node) -
  invoke `git-toolkit:git-ops` (read-only) for a full-patch diff of the run's changed modules between
  the run's base and `HEAD`, inside the `<path>/run-integration` worktree; per
  `${CLAUDE_PLUGIN_ROOT}/skills/run-harness/references/run-integration.md` § Pre-PR tail (stage
  order position 2), scanned ONCE for the whole run, never per module.

Consider only CHANGED lines (leading `+` or `-`, excluding the `+++`/`---` file headers). A signal HITS
on ANY match; record the fired set as a FIELD, never as raw grep output (discipline:
`odoo-diff-comparator`'s `deferred_work_due` / `deferred_work_unanchored` fields are the shape
to copy).

| # | fires when a changed line ... |
|---|---|
| S1 | belongs to a path matching `i18n/.*\.(po|pot)$` |
| S2 | is in a `.py` file and contains `_(` or `_lt(` |
| S3 | is in a `.py` file and contains `string=`, `help=`, or `selection=` |
| S4 | is in an `.xml` file and contains `string=`, `help=`, `placeholder=`, `confirm=`, `title=`, `add-label=`, `sum=`, or `avg=` |
| S5 | is in an `.xml` file under `views/`, `report/`, `data/`, `templates/`, or `static/src/xml/` and changes non-whitespace TEXT between tags (`>text<`) |
| S6 | is in a `.js` file and contains `_t(` or `_lt(` |
| S7 | sets `field_description`, `subject`, `body_html`, `body`, `note`, `description`, or `name` on a record (any `.xml` or `.csv`) |
| S8 | is in `__manifest__.py` and touches the `name`, `summary`, or `description` key |

Record `i18n_signals: [S1,S4]` (the fired ids) or `i18n_signals: none`. **Ambiguity counts as a HIT** -
the asymmetry is deliberate: a false positive costs one reconcile pass that finds nothing, while a false
negative ships a broken catalog. Do not re-derive that trade-off per call.
