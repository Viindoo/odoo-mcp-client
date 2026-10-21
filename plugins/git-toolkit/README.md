# git-toolkit

A safe, scale-aware **git + GitHub toolkit for AI agents**. One front-door skill (`git-ops`) takes
any git/github request, runs it in a delegated agent so the calling agent's context stays clean,
and never loses code - from a few lines up to thousands of files.

Licensed **Apache-2.0**. Part of the [`odoo-mcp-client`](https://github.com/Viindoo/odoo-mcp-client)
monorepo, but domain-agnostic: it has no Odoo dependency.

## What it does

- **One skill, `git-ops`** - the universal front door. Fires on git intent (status/log/diff/blame/
  bisect, branch/tag/worktree, fetch/pull/merge/cherry-pick, rebase, forward-port/backport,
  conflict resolution, history rewrite, recovery, large-diff analysis) and GitHub intent (PR/issue/
  review/release/CI/fork), in whatever language the user writes.
- **Request in, result out.** The caller describes what it wants and what it needs back; it never
  writes git or gh commands. Every op, a one-line read included, goes to an agent that owns the
  commands and the safety steps:
  - a read -> `git-surveyor`; a local mutation -> `git-operator`; a GitHub op -> `github-operator`.
  - a large change (>500 files / >10k LOC / multi-commit rewrite) -> `git-pipeline-lead`, which runs
    map -> evaluate -> strategy -> execute -> verify below the caller.
- **Never loses code** - destructive ops back up first and verify tree-identity after. A human
  confirms only one op: changing a protected branch without a pull request.
- **One plain command per call** - every git call is `git -C <worktree> <subcommand> <args>`, and
  a dirty tree stops the op instead of being stashed.
- **Scales** - never reads a huge diff whole; clusters by module and delegates per cluster; supports
  sparse-checkout / partial-clone / LFS.
- **MCP-first GitHub** - prefers the GitHub MCP tools, falls back to the `gh` CLI.
- **Convention-aware commits** - detects the repo's commit convention and writes business-outcome
  subjects, signs off only when the repo requires it, and reports every subject it rewrote.

## Agents

| Agent | Role | Spawns? | Tools |
|---|---|---|---|
| `git-surveyor` | read-only cognition (map / evaluate / verify) | no | Read, Grep, Glob, Bash (gh read-only); no GitHub MCP |
| `git-operator` | local mutation (integration + destructive rewrite) | no | Read, Grep, Glob, Edit, Write, Bash |
| `github-operator` | GitHub API (MCP-first / gh-fallback) | no | Read, Grep, Glob, Bash + GitHub MCP |
| `git-pipeline-lead` | orchestrator for large changes (runs P1-P5) | yes (only spawner) | all |

Only `git-pipeline-lead` can spawn sub-agents; the leaves cannot. This depth guard caps nesting at
two levels (lead -> leaf).

A launcher collects a leaf's result according to the agent-launch tool it holds (rule N0 in
`snippets/git-nesting-protocol.md`). Where the launch tool has a `run_in_background` parameter, the
launcher passes `false` and the result returns inside the turn (independent leaves go out in one
message). Where the launch tool has no such parameter, the launcher launches, ends its turn, and is
woken once per leaf.

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
