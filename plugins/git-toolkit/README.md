# git-toolkit

A safe, scale-aware **git + GitHub toolkit for AI agents**. One front-door skill (`git-ops`) takes
any git/github request, runs it in a delegated or inline-bounded context so the calling agent's
context stays clean, and never loses code - from a few lines up to thousands of files.

Licensed **Apache-2.0**. Part of the [`odoo-mcp-client`](https://github.com/Viindoo/odoo-mcp-client)
monorepo, but domain-agnostic: it has no Odoo dependency.

## What it does

- **One skill, `git-ops`** - the universal front door. Fires on git intent (status/log/diff/blame/
  bisect, branch/tag/worktree, fetch/pull/merge/cherry-pick, rebase, forward-port/backport,
  conflict resolution, history rewrite, recovery, large-diff analysis) and GitHub intent (PR/issue/
  review/release/CI/fork). EN + VI triggers.
- **Three execution modes**, chosen by output size and risk:
  - **INLINE** - bounded, low-risk reads (`git status`, `git log -n`) run directly.
  - **SINGLE-DELEGATE** - one medium op cold-spawns one leaf agent.
  - **PHASED-PIPELINE** - a large change (>500 files / >10k LOC / multi-commit rewrite) cold-spawns
    `git-pipeline-lead`, which runs map -> evaluate -> strategy + human-confirm -> execute -> verify
    below the caller.
- **Never loses code** - destructive ops back up first, verify tree-identity after, and stop at a
  human-confirm gate before running.
- **Scales** - never reads a huge diff whole; clusters by module and delegates per cluster; supports
  sparse-checkout / partial-clone / LFS.
- **MCP-first GitHub** - prefers the GitHub MCP tools, falls back to the `gh` CLI.
- **Convention-aware commits** - detects the repo's commit convention and writes business-outcome
  subjects, with DCO sign-off when required.

## Agents

| Agent | Role | Spawns? | Tools |
|---|---|---|---|
| `git-surveyor` | read-only cognition (map / evaluate / verify) | no | Read, Grep, Glob, Bash (git read) + GitHub MCP read |
| `git-operator` | local mutation (integration + destructive rewrite) | no | Read, Grep, Glob, Edit, Write, Bash |
| `github-operator` | GitHub API (MCP-first / gh-fallback) | no | Read, Grep, Glob, Bash + GitHub MCP |
| `git-pipeline-lead` | orchestrator for large changes (runs P1-P5) | yes (only spawner) | all |

Only `git-pipeline-lead` can spawn sub-agents; the leaves cannot. This depth guard caps nesting at
two levels (lead -> leaf).

## Dependency + auth

`git-toolkit` depends on the `github` plugin (auto-installed from the default
`claude-plugins-official` marketplace), which provides the `mcp__plugin_github_github__*` tools over
HTTP (`https://api.githubcopilot.com/mcp/`, Copilot-gated).

- GitHub MCP needs `GITHUB_PERSONAL_ACCESS_TOKEN` set in the environment.
- The `gh` CLI (its own `gh auth login`) is the **always-available** fallback. Do not expect the
  MCP path to work on a bare PAT without Copilot access - `gh` covers that gap.

## Install (from this checkout, no marketplace)

```bash
claude --plugin-dir ./plugins/git-toolkit
```

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the routing, depth-guard, and safety-gate
diagrams. The runtime contract lives in the snippets (SSOT) and the `references/` recipes.
