<!-- SSOT snippet. The single home for the MANDATORY i18n reconcile step its two callers share:
     the mandate wording, the enumerated escapes, and the decidable trigger. Edit here only;
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

**Caller obligations (all four, or the mandate is unsound):**
1. Pass `WORKTREE_PATH` - the worktree the adapt wrote. `.po`/`.pot` are git-tracked and
   `odoo-translator` is a separate agent context that does not inherit cwd.
2. Pass an `INSTANCE_HANDLE` (or `SELF_PROVISION: worktree-addons`) whose addons path covers that
   worktree, so the export reads POST-ADAPT code
   (`${CLAUDE_PLUGIN_ROOT}/snippets/instance-handle-contract.md` § Addons coverage assertion). An
   instance on the principal checkout makes a worktree-only `msgid` surface as nothing and the loss is
   committed unseen.
3. Pass explicit `TARGET LANGUAGES`, so `odoo-i18n` P0's tier-5 locale default is unreachable.
4. Present the returned result at YOUR OWN existing human gate - do NOT let `odoo-i18n` open a separate
   STOP per invocation. A mandated step that always stops is a deadlock.

## Escape hatches (ENUMERATED - no others; every skip RECORDED, never silent)

| # | condition (mechanical) | record verbatim | status |
|---|---|---|---|
| E1 | the unit's verdict is DELETE-absorbed or OBSOLETE | `i18n: n/a (module deleted)` | proceed |
| E2 | the module ships no `i18n/` directory AND the trigger table below fires ZERO signals | `i18n: n/a (no catalog, no translatable delta)` | proceed |
| E3 | tiers 1-4 of language resolution all empty (caller passed none and none inferable) | `i18n: not-applicable (no target language resolvable from tiers 1-4)` | proceed |
| E4 | forward-port only: `installable_false == yes` for this module (the lint-only lane) | `i18n: n/a (installable:False at target - lint-only lane)` | proceed |
| E5 | no instance can be provisioned | `i18n: blocked (no instance)` | **BLOCKED** |
| E6 | the instance's addons path does not cover `WORKTREE_PATH` | `i18n: blocked (instance addons-path excludes the worktree)` | **BLOCKED** |

Anything not in this table is NOT an escape. "The diff looked label-free" is not an escape - that is
E2, and E2 requires BOTH conditions.

## Condition 2 - forward-port's already-upgraded test (decidable, no new probe)

Read `installable_false` from the module's row in `merge-log.md` - the verbatim `merge_log_line` the
prober emitted, coerced to `yes`/`no`. `installable_false == no` -> the module is live at the target and
the mandate applies. `== yes` -> E4. Categories 1-2 the orchestrator resolved itself without a probe:
read the same `yes`/`no` it recorded. Neither present -> **BLOCK**; do not guess and do not re-probe.
`installable_false` is the ONE field this condition reads - do not substitute any other field name
(internal-only, prober-side values are never persisted and no consumer parses them by name).

## Trigger table - "touches translatable terms" (forward-port condition 1 only)

Scan the ALREADY-MATERIALIZED per-commit dumps for this batch -
`<ISOLATE_DIR>/forward-port/<slug>/commits/<sha>.dump` (full patch: message + diff). Consider only
CHANGED lines (leading `+` or `-`, excluding the `+++`/`---` file headers). A signal HITS on ANY match;
record the fired set as a FIELD, never as raw grep output (discipline:
`${CLAUDE_PLUGIN_ROOT}/agents/odoo-diff-comparator.md`, whose `deferred_work_due` /
`deferred_work_unanchored` fields are the shape to copy).

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
