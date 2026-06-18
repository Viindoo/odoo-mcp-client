<!-- SSOT snippet. Referenced (not copy-pasted) by odoo-run-forward-port (Phase 2 classify),
     odoo-intent-extractor (outcome labeling), odoo-coder FP-enriched adapter brief, and any
     spawned worker that must classify a forward-port commit before touching the git index.
     Edit here only; consumers point at ${CLAUDE_PLUGIN_ROOT}/snippets/fp-intent-4outcome.md. -->

# Forward-Port 4-Outcome Classification Contract

When forward-porting, each commit carries an **intent** (the behavior/purpose/fix being
forwarded). Before touching any code, classify that intent against the **target platform**
into exactly one of four buckets. This is a **business-level decision** - not a merge
decision. Get it wrong here and every downstream step (merge, adapt, verify) is wasted or
destructive.

## The four buckets

| # | Name | Signal | Action |
|---|---|---|---|
| (a) | **Already satisfied** | Target platform provides the behavior natively | Skip adapt code; still merge to advance merge-base - see [[fp-merge-absorption]] |
| (b) | **Still needed - mechanism compatible** | Intent survives; target APIs are compatible | 3-way merge + adapt to target idioms |
| (c) | **Still needed - mechanism gone** | Intent survives; the specific API/hook/field was removed or replaced | Re-implement from scratch using target idioms; oracle = forwarded source test |
| (d) | **No longer relevant** | Was a workaround for a source-version bug/limitation the target platform no longer has | Skip adapt code; still merge to advance merge-base - see [[fp-merge-absorption]] |

## How to classify - grounding via odoo-semantic-mcp (mandatory)

**Do not classify from memory or by reading old code alone.** Pin the target version, then
probe every symbol the intent touches:

```
# 1 - pin target
set_active_version(odoo_version='17.0')   # or '18.0' - always explicit

# 2 - diff the API at source vs target for each touched symbol
api_version_diff(symbol='account.move._post', from_version='16.0', to_version='17.0')

# 3 - inspect the model/field at target
model_inspect(model='account.move', method='summary', odoo_version='17.0')
```

- If a field or method **is present at target** with compatible signature -> bucket (b).
- If it **was removed or structurally replaced** (different model, renamed field, new OWL
  component) -> bucket (c).
- If the target already ships the exact behavior (new built-in, merged upstream, refactored
  core) and the forwarded test turns green without any adapt code -> bucket (a).
- If the source behavior was a compensating fix for a bug or platform limit that no longer
  exists in target -> bucket (d).

**Bucket (a) evidence gate:** forward the source test to target syntax, run it. GREEN with
zero adapt code = confirmed (a). If it needs any code change to pass, it is (b) or (c).

**`odoo_version=` is mandatory** in every odoo-semantic-mcp call above - never omit it and
never rely on a default.

## Worklog entry - one row per commit

Append to the shared `merge-log.md` after classifying each commit:

| Commit SHA | Intent summary | Bucket | Reason | Evidence (file:line or OSM citation) |
|---|---|---|---|---|
| `abc1234` | Prevent double-post on `account.move` | (b) | `_post` present at target, signature compatible | `model_inspect account.move @17.0 - _post exists` |
| `def5678` | Guard against `res.partner.comment` Html/Text mismatch | (c) | field type changed - `api_version_diff` shows `Html->Text` at 17.0 | `api_version_diff res.partner.comment@16->17` |
| `ghi9012` | Patch: bypass ORM lazy-load bug fixed in v17 | (d) | core bug resolved in 17.0 - no equivalent trigger | OSM `lookup_core_api` + issue link |

Do not leave a row blank in the Reason or Evidence columns. "No data" is not acceptable -
probe until you have a citation.

## Cross-references

- [[fp-symbol-survival-check]] - per-symbol existence check after `git merge --no-commit`
  (catches autosilent field breaks that git does not flag as conflicts)
- [[fp-merge-absorption]] - why outcome (a) and (d) still generate a merge commit
- [[osm-first-contract]] - full grounding protocol (Tier 1/2/3 fallback when OSM is down)
