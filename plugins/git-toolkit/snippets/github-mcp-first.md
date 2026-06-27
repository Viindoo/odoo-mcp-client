<!-- SSOT snippet. The single home for the GitHub MCP-first / gh-CLI-fallback policy and the
     exact tool prefix. Referenced via ${CLAUDE_PLUGIN_ROOT}/snippets/github-mcp-first.md by
     the skill and by github-operator. Edit here only. -->

# GitHub MCP-first Policy (SSOT)

For all GitHub API work, the GitHub MCP server is the PRIMARY interface; the `gh` CLI is the
FALLBACK. Never invoke both for the same operation.

## G1 - The tool prefix (exact)

GitHub MCP tools are named `mcp__plugin_github_github__*` at runtime - this exact prefix, nothing
else. Examples: `mcp__plugin_github_github__pull_request_read`,
`mcp__plugin_github_github__create_pull_request`, `mcp__plugin_github_github__issue_write`,
`mcp__plugin_github_github__search_code`. Any other spelling is a bug.

These ship from the `github` plugin (declared as a dependency, auto-installed from the default
`claude-plugins-official` marketplace). The server is an HTTP endpoint
(`https://api.githubcopilot.com/mcp/`) authenticated by the `GITHUB_PERSONAL_ACCESS_TOKEN` env var
and is Copilot-gated.

## G2 - Precedence

1. Use `mcp__plugin_github_github__*` as PRIMARY for: PR create/read/review/merge, issue
   read/write/comment, branch/commit/tag queries, file reads, search, releases.
2. Fall back to `gh` (`gh pr ...`, `gh issue ...`, `gh release ...`, `gh api ...`) ONLY when the
   MCP tool returns an error, is unavailable (tool not in scope / token absent), or the operation
   has no MCP equivalent.
3. Never invoke both for one operation.
4. When the `gh` fallback was used, note `DONE_WITH_CONCERNS` so the caller knows the MCP path was
   degraded.

## G3 - MCP-vs-gh strengths (route by them)

- MCP is best for INTELLIGENCE: context-aware PR creation, reading a review thread to reply,
  inline review comments, PR-with-full-diff review.
- `gh` is best for AUTOMATION: CI scripting, batch ops, fork -> PR upstream
  (`gh pr create --repo`), and anything needing script-safe exit codes.

## G4 - Token absent

git-toolkit cannot supply `GITHUB_PERSONAL_ACCESS_TOKEN` (it is the `github` plugin's auth). If the
MCP server is unreachable because the token is unset, fall back to `gh` (which carries its own auth
via `gh auth login`). If neither is authenticated, STOP and return NEEDS_CONTEXT naming the missing
credential - do not guess or retry blindly.
