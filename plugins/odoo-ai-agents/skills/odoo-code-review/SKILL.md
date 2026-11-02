---
name: odoo-code-review
argument-hint: "[PR#|local|worktree:<path>]"
description: >-
  Static review of Odoo code, a diff or a PR: bugs, conventions, security
---

## Role

Front door for reviewing Odoo code. It resolves the target, computes the changed set, launches
`odoo-code-reviewer` in its three modes at three tiers, and returns the verdict. It launches and
returns; it does not wait on a fix, and the findings go back to the coder that built the node
through the caller's fix round. Every review mode judges the change against
`${CLAUDE_PLUGIN_ROOT}/snippets/odoo-platform-design-principles.md` § 0: a block on a policy
limit, a guard without a way out, or a surface that behaves unlike core's is a finding.

## Out of Scope

- **Writing new code or fixing a finding** -> `odoo-coding` (the caller resumes the node's coder)
- **Module-level pre-upgrade audit** -> `odoo-deprecation-audit`
- **Override safety analysis of one hook** -> `odoo-override-finding`
- **Verifying a render error in a real browser** -> `odoo-debug`
- **Rating a rendered screen's look, UX or accessibility** -> `odoo-ui-review`
- **Executing acceptance scenarios on a live instance** -> `odoo-acceptance`

## Target

| User intent | `TARGET` |
|---|---|
| "review this" on the working tree | `local` |
| "review PR #N" or a GitHub PR URL | `pr:<N>` |
| work in another worktree, a node's worktree, an integration branch | `worktree:<abs-path>` (required; without it a review of the principal cwd finds an empty diff) |
| a pasted block or one file with no git context | `file:<path>` - R1 and R2 over that file only |

## Steps

1. **Resolve the tree.** `local` -> the `repo_root` of a `repo_facts` call on this cwd; `worktree:` -> the path given; `pr:` ->
   invoke `git-toolkit:git-ops` to fetch the PR metadata and changed files and to check the PR
   branch out in a worktree at the path `project_dir` (axis `worktree`, `name` = `pr-<N>`)
   returns - under the state root, never a temp dir and never the principal checkout
   (git-safety-contract S9). Capture `SHARE_DIR` and `ISOLATE_DIR` once with `project_dir`
   against that tree.
2. **Changed set.** Ask `git-toolkit:git-ops` for the files that differ between `BASE` (default the
   series main branch, or the PR base) and the tree's HEAD, and for the diff of that range written
   to `<ISOLATE_DIR>/reviews/<slug>-<date>/diff.patch` (`DIFF_PATH`); the files give `CHANGED_SET`; the modules it touches and their manifests give
   the Domain line when the brief carries none (`${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`).
   Delete `<ISOLATE_DIR>/reviews/<slug>-<date>/` directories untouched for 30 days
   (`${CLAUDE_PLUGIN_ROOT}/snippets/visual-evidence-lifecycle-contract.md` Clause 3).
3. **Launch R1** (`odoo-code-reviewer`, `MODE: R1`, `model: haiku`) with the brief in
   `${CLAUDE_PLUGIN_ROOT}/skills/odoo-code-review/references/agent-prompts.md`. A diff whose
   changed files exceed one agent's budget is split by module into several R1 launches in one
   message.
4. **Launch R2, and R3 when due**, in ONE message after R1 returns: R2 (`MODE: R2`,
   `model: sonnet`) with `R1_FINDINGS`; R3 (`MODE: R3`, `model: opus`) only when the unit's
   `business_function` is on the specialist list of the taxonomy or `RECON` records an override
   chain or dependent count at the thresholds of
   `${CLAUDE_PLUGIN_ROOT}/skills/_shared/concurrency-guard.md` § 5.2. When R3 runs, R2 is
   launched after R3 returns, with `R3_FINDINGS`, so one report carries the verdict. When an
   `INSTANCE_HANDLE` is available and `CHANGED_SET` holds views, launch `odoo-ui-reviewer`
   (`model: sonnet`) in the same message as R2 for the rendered screens; R2 reads its report
   path when both are given.
5. **Return.** The R2 report path, verdict and score, the severity counts, and the Continuation
   Contract (`next: odoo-ui-review` when R2 asked for it). Present the summary in the user's
   language. Post to the PR only on the explicit keyword `post`: convert every finding row to
   `{path, startLine, line, severity, body, suggestion}` and invoke `git-toolkit:git-ops` to open
   one pending review, one inline comment per finding, submitted as `REQUEST_CHANGES` when any
   CRITICAL or HIGH remains, else `COMMENT`, plus one top-level verdict comment.

## A later round

The caller sends the fix diff to the SAME reviewers with `SendMessage` (`PRIOR_FINDINGS` = their
earlier reports), never to a new launch; R1 verifies its own findings, R2 verifies its own and
re-issues the verdict. Acceptance failures go to R2 as `ACCEPTANCE_EVIDENCE` for classification.
Three rounds per change; a fourth stops with the remaining findings for the human.

## Artifacts

Under `<ISOLATE_DIR>/reviews/<slug>-<date>/`: `r1-findings.md`, `r3-findings.md` (when R3 ran),
`ui-review-<module>.md` (when the UI reviewer ran), `review.md` (R2: findings, criteria table,
verdict, score).

## Standalone-first fallback

OSM unreachable: each mode grounds from the tree per
`${CLAUDE_PLUGIN_ROOT}/snippets/disk-fallback-protocol.md` and the report says
`grounded: local-source`; R1's existence checks use grep over the checkout.

## Agent-managed tools

`odoo-code-reviewer` (three modes) and, conditionally, `odoo-ui-reviewer`. The reviewer invokes
the three audit skills inline for its own escalation and launches nothing.

## Continuation Contract

Append the block of `${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md`: `produced` = the
report paths; `next` = `odoo-ui-review` when R2 requested it; `status: DONE` with the verdict.
