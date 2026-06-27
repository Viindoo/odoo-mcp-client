# Compression Report - git-toolkit

Semantic-preserving compression of runtime docs (agents / git-ops skill / references / snippets /
docs). Branch `chore/compress-plugin-docs`. Token estimate = words / 0.75.

## Before -> After (token)

| Scope | Files in scope | Compressible | Changed | Words before -> after | Tokens before -> after | Saved |
|---|---|---|---|---|---|---|
| git-toolkit | 19 | 19 | 14 | 11,066 -> 10,901 | ~14,754 -> ~14,534 | **~220 tok (1.49%)** |

Status: 5 compressed, 9 light, 5 skipped.

## What was compressed (3 layers, body only)

1. **Semantic** - connective prose trimmed in `git-safety-contract.md` (around S1-S9), agent
   prologues, `git-ops/SKILL.md` step narration, `architecture.md` prose around the mermaid diagrams.
2. **Within-file dedup** - `git-operator.md` S9 worktree/principal-lock invariant consolidated
   (was restated 4x) to one canonical statement + reference.
3. **Inline-copy -> pointer** - `large-change-pipeline.md` P5 "intentionally changes content"
   paragraph (verbatim copy of safety-contract S6) -> pointer; `commit-convention-general.md`
   "Subject rules" -> pointer to the snippet.

## Preservation - verified

- **0** frontmatter `name`/`description` changes (incl. `github-operator` tools allowlist) across all
  14 changed files (independent byte-diff vs `master`).
- All bash recipes, MCP-vs-gh tool-id tables, commit detection regexes, S1-S9 / 8-item human-confirm
  gate, M2 scale thresholds, mermaid diagrams kept verbatim.
- **0** introduced dangling links; **0** files reverted.
- Behavior gate GREEN with the monorepo suite (`make validate` + `make test`: 946 passed, 2 skipped).

## Skipped / light (no safe compression)

`history-rewrite.md`, `conflict-resolution.md` (bash recipes), `github-pipeline.md` (tool-id tables),
`git-scale-protocol.md` (numeric thresholds) - command/data-dense, ~0% safe prose yield.

## Honest note on yield

git-toolkit is a thin prose routing layer where ~40-50% of weight is non-compressible by contract
(frontmatter triggers, tools array, bash, tables, mermaid). Realized 1.49% is small but verified-safe.

## Pre-existing issues flagged (NOT fixed - out of scope)

- `docs/architecture.md` references `snippets/git-delegation.md`, but this plugin's snippet is named
  `snippets/git-delegation-decision.md` (likely a pre-existing broken link in `master`).
