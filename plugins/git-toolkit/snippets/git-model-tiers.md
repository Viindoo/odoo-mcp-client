<!-- SSOT snippet. The single home for git-toolkit model-tier vocabulary, the single-delegate
     op-class -> tier map (first-match-wins), and the dispatch convention (param + DISPATCH MODEL
     line). The phased-pipeline per-phase map lives in git-nesting-protocol.md N3.
     Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/git-model-tiers.md. Edit here only. -->

# Git Model Tiers (SSOT)

Model tiers in git-toolkit are assigned by cognitive load and reversibility. The goal is to pay
the right token budget per op: cheap for mechanical reads, standard for bounded mutations and
reasoning, premium only for irreversible history rewrites or high-stakes integration.

git-toolkit does NOT author application code, so the `fable` tier is not used here.

## Tier vocabulary

| Tier | When to use |
|---|---|
| `haiku` | Mechanical reads and pure enumeration - name-only/numstat lists, file-to-module mapping, commit counts. Cheapest and fastest. |
| `sonnet` | DEFAULT floor for single-delegate ops. Diff-content reasoning, bounded reversible git mutation (fetch/pull-rebase/merge/cherry-pick/branch/tag/worktree/non-force push), and standard GitHub API ops requiring judgment. |
| `opus` | Destructive history rewrites (interactive rebase, squash, split, amend, reset, filter-repo, force-with-lease push) AND high-conflict or large integration ops where P3 strategy synthesis is required. |

## Single-delegate op-class -> tier map

First-match-wins. Read from the top; stop at the first row that matches the op.

| # | Op class (first match wins) | Agent | Tier |
|---|---|---|---|
| 1 | Destructive history rewrite (interactive rebase, squash, split, amend, reset, filter-repo, force-with-lease push) OR a high-conflict / large integration | `git-operator` | opus |
| 2 | Bounded reversible integration (fetch, pull-rebase, simple merge, cherry-pick range, branch/tag/worktree, non-force push) | `git-operator` | sonnet |
| 3 | Read-only git cognition that REASONS over diff content (analyze a diff, assess conflict/risk/intent, range-diff / no-loss proof) | `git-surveyor` | sonnet |
| 4 | Pure mechanical enumeration (name-only/numstat lists, file->module map, commit counts) | `git-surveyor` | haiku |
| 5 | GitHub API op needing judgment (review a PR diff + post findings, triage an issue) | `github-operator` | sonnet |
| 6 | GitHub API mechanical op (read PR/issue, list, CI status, create release/tag, fork) | `github-operator` | haiku |

## Dispatch convention

On a single-delegate dispatch, the CALLER (the git-ops skill or orchestrator) MUST:

1. Match the op against the table above (first-match-wins) to get the tier.
2. Pass the resolved tier as the Agent-tool `model` parameter.
3. Put `DISPATCH MODEL: <tier>` as the FIRST LINE of the brief (belt-and-braces guard so the
   agent can verify its own tier and the reviewer can audit the dispatch).

Do NOT rely on the agent's frontmatter `model:` default or on `inherit` for the final tier - both
can be overridden by environment or caller context.

Precedence (highest to lowest): env `CLAUDE_CODE_SUBAGENT_MODEL` > Agent-tool `model` param >
agent frontmatter `model:` > `inherit`. The Agent-tool `model` param is therefore the authoritative
lever for single-delegate tier control.

## Phased-pipeline per-phase tiers

The per-phase model map for the phased pipeline (P1 MAP through P5 VERIFY) lives in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N3. Do not duplicate it here.
