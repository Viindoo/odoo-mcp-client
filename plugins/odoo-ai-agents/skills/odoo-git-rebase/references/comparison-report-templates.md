# odoo-diff-comparator - rebase findings files

## Rebase comparison -> `<ISOLATE_DIR>/git-rebase/<slug>/comparison.md`

One row per commit not already present, with the failure mode of
`${CLAUDE_PLUGIN_ROOT}/snippets/rb-intent-4outcome.md`: `already-present`, `renamed`, `moved`,
`override-refactored`, `depends-drift`, `test-symbol-removed` or `clean`.

```markdown
# Cluster behavior comparison - <slug>

**Mode:** rebase
**Diff scope:** <new-base>...<feature-ref>
**grounded:** <osm | local-source | ungrounded>

## Per-commit comparison

| SHA | Intent (one-liner) | Proposed outcome | Failure mode | Evidence | Proposed adapt |
|---|---|---|---|---|---|
| `<sha>` | <from the intent record> | (a)/(b)/(c)/(d) | <mode or none> | `<symbol> @ <path>` | <"no action" / "skip" / brief note> |

## Duplicate-behavior risk list
<each intent the new base already implements, so the feature would be defined twice: sha, symbol, path on the new base>

## Grounding notes
<index misses, local-source fallbacks>
```

## Rebase verify -> `<ISOLATE_DIR>/git-rebase/<slug>/verify.md`

```markdown
# Range-diff + dup-guard verify - <slug>

**Mode:** rebase-verify
**grounded:** <osm | local-source | ungrounded>

## Range-diff verdict

| Old commit | New commit | Status | Assessment |
|---|---|---|---|
| `<sha>` | `<new sha>` or (dropped) | `=` / `<` / `>` | <intent preserved / expected: already present / ...> |

## Duplicate-behavior findings
<per key identifier of a feature (a guard field, a constraint, a marker): how many definitions the index finds across the whole inheritance chain. More than one is a BLOCKER, even when the second lives in another module; a search inside the module only locates the one definition>

## Overall verdict
PASS / FAIL - <one-line reason>
```
