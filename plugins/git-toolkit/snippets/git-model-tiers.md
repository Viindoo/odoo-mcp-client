<!-- SSOT snippet. The single home for git-toolkit model-tier vocabulary, the single-delegate
     op-class -> tier map (first-match-wins), and the dispatch convention (param + DISPATCH MODEL
     line). The phased-pipeline per-phase map lives in git-nesting-protocol.md N3.
     Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/git-model-tiers.md. Edit here only. -->

# Git Model Tiers (SSOT)

Model tiers in git-toolkit are assigned by the kind of work and its reversibility: haiku for
anything a cheap model does reliably (reads, enumeration, reasoning over a diff, GitHub API ops,
conflict-free bounded integration), sonnet where an error is costly or judgment is needed
(destructive rewrites, conflict resolution, correctness reviews, the no-loss verify), opus only
for strategy synthesis. Context size never decides the tier.

git-toolkit does NOT author application code, so the `fable` tier is not used here.

## Tier vocabulary

| Tier | When to use |
|---|---|
| `haiku` | Read, enumerate, or reason over a diff (name-only/numstat lists, file-to-module mapping, commit counts, assessing a scoped diff); GitHub API ops including issue triage; bounded CONFLICT-FREE integration (fetch, branch, tag, worktree, non-force push, a clean cherry-pick or merge). If a conflict surfaces mid-op, stop and re-dispatch at `sonnet`. |
| `sonnet` | Destructive rewrite (interactive rebase, squash, split, amend, reset, filter-repo, force-with-lease push); conflict resolution; a PR review that judges correctness; the no-loss verify that gates an irreversible step. |
| `opus` | ONLY the pipeline lead's strategy synthesis (P3) for a port across major versions, or after a sonnet lead returned BLOCKED at P3. |

The safety contract (backup, tree-identity, human-confirm) is unchanged at every tier.

## Single-delegate op-class -> tier map

First-match-wins. Read from the top; stop at the first row that matches the op.

| # | Op class (first match wins) | Agent | Tier |
|---|---|---|---|
| 1 | Launching `git-pipeline-lead` - the CALLER decides before launch, the lead never picks its own tier: opus for a port ACROSS major versions (backport / forward-port), whose P3 strategy is the hard part; sonnet for every other pipeline. A sonnet lead that returns BLOCKED at P3 is re-launched once at opus | `git-pipeline-lead` | opus for a cross-version port, else sonnet |
| 2 | Destructive history rewrite (interactive rebase, squash, split, amend, reset, filter-repo, force-with-lease push), or any integration that is resolving conflicts | `git-operator` | sonnet |
| 3 | Bounded conflict-free integration (fetch, branch/tag/worktree, non-force push, clean cherry-pick or merge) - a conflict mid-op means re-dispatch at sonnet | `git-operator` | haiku |
| 4 | Read-only no-loss verify (tree-identity, range-diff) that gates an irreversible step | `git-surveyor` | sonnet |
| 5 | Other read-only git cognition: enumerate, map, analyze a diff, assess conflict/risk/intent | `git-surveyor` | haiku |
| 6 | GitHub API op that judges correctness (review a PR diff and post findings) | `github-operator` | sonnet |
| 7 | Other GitHub API op (read, list, issue triage, CI status, create PR/release/tag, fork) | `github-operator` | haiku |

## Dispatch convention

On a single-delegate dispatch, the CALLER (the git-ops skill or orchestrator) MUST:

1. Match the op against the table above (first-match-wins) to get the tier.
2. Pass the resolved tier as the launch's `model` parameter.
3. Put `DISPATCH MODEL: <tier>` as the FIRST LINE of the brief (so the reviewer can audit the
   dispatch).

Do NOT rely on the agent's frontmatter `model:` default or on inheritance for the final tier.

Precedence (highest to lowest): agent-launch `model` param > agent frontmatter `model:` > env
`CLAUDE_CODE_SUBAGENT_MODEL` > the calling context's model (inherit). The agent-launch `model` param
is therefore the authoritative lever for single-delegate tier control.

## Phased-pipeline per-phase tiers

The per-phase model map for the phased pipeline (P1 MAP through P5 VERIFY) lives in
`${CLAUDE_PLUGIN_ROOT}/snippets/git-nesting-protocol.md` N3. Do not duplicate it here.
