# Rebase 4-outcome classification (same series)

Each commit replayed onto a new base of the same series carries an intent. Before touching code,
classify that intent against the base HEAD into one bucket - a business decision, not a merge
decision.

| # | Bucket | Signal | Action |
|---|---|---|---|
| (a) | Already satisfied | the base already ships the behaviour; re-applying would duplicate it | skip the commit through `git-toolkit:git-ops`; record the reason in `rebase-log.md` |
| (b) | Adapt and apply | the intent survives; the base renamed, moved or refactored what the commit touches | replay the intent in the base's idiom, never the old diff verbatim |
| (c) | Re-implement | the base made the original diff irrelevant or unsafe; the intent is still needed | rebuild from the base's idioms; the oracle is the forwarded source test |
| (d) | Drop | the base's design removed the need | drop the commit; record reason and evidence in `rebase-log.md` |

## Classifying

Classify from the state of the base, never from memory or the old diff alone: for every symbol the
commit touches, at the shared series (the version passed on every OSM call), does it exist with a
compatible signature, was it renamed or moved, is the behaviour already there?

**(a) needs evidence:** each key identifier (field, method, XML id, security rule) has exactly
one definition on the base and that definition covers the intent. Any code change still needed
makes it (b) or (c). A confirmed (a) is skipped in the rebase and never sent to `odoo-coding`.

## What git does not show

None of these leaves a conflict marker; the defect appears at runtime or in a test run.

| Failure mode | Symptom |
|---|---|
| Feature already present | a field, method or rule defined twice; behaviour fires twice or the ORM raises |
| Symbol renamed on base | clean merge, then `NameError` / `AttributeError` |
| Code moved on base | the patch edits a stale path; the moved code is untouched |
| Override point refactored | `super()` skips, or recurses into the wrong chain |
| Manifest depends drift | `ImportError` or a missing model at install |
| Test symbol removed | `setUpClass` errors, misread as green |

## Duplicate-behaviour guard

After replaying a (b) or (c) commit and before its files are staged: count the definitions of each
key identifier across the WHOLE inheritance chain, in every module, with the index. More than one
means the commit silently hit (a) - possibly through a definition in another module, which a
search inside one module cannot see: a blocker. Remove the duplicate, switch the log row to (a)
and name the base commit and module that already provide the behaviour. A search inside the module
only locates the one definition.

## Log

One row per commit in `rebase-log.md`, Reason and Evidence never blank:

| Commit SHA | Intent summary | Bucket | Reason | Evidence (file:line or OSM citation) |
|---|---|---|---|---|

The cross-series analogue is `fp-intent-4outcome.md`.
