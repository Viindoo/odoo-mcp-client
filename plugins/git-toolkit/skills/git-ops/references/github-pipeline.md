# GitHub pipeline recipes - MCP-first

All GitHub ops follow `${CLAUDE_PLUGIN_ROOT}/snippets/github-mcp-first.md`: the
`mcp__plugin_github_github__*` tools are PRIMARY; `gh` is the fallback; never both for one op; note
`DONE_WITH_CONCERNS` when `gh` was used. Unbounded reads (a PR body, a diff, a long issue thread)
are summarized to a findings file - never echoed whole to the caller.

**Bare URL default:** when handed a PR or issue URL with no further instruction, `github-operator`
returns a compact digest only (number, title, author, state, CI, +/- lines for PRs; title, state,
labels for issues) - the full body/diff is fetched only on explicit request.

## PR lifecycle

| Step | MCP (primary) | gh (fallback) |
|---|---|---|
| Read PR + diff | `pull_request_read` | `gh pr view <n>` / `gh pr diff <n> --name-only` |
| List PRs | `list_pull_requests` | `gh pr list` |
| Create PR | `create_pull_request` | `gh pr create` |
| Edit PR | `update_pull_request` | `gh pr edit <n>` |
| Review (approve / request-changes / comment) | `pull_request_review_write` | `gh pr review <n>` |
| Inline review comment | `add_comment_to_pending_review` | (no equivalent) |
| Reply to a thread | `add_reply_to_pull_request_comment` | (limited) |
| Merge | `merge_pull_request` | `gh pr merge <n> --squash/--merge/--rebase` |
| Update branch from base | `update_pull_request_branch` | `gh pr update-branch <n>` |

Scale: for a large PR, read `--name-only` first, cluster, then read scoped diffs - obey
`${CLAUDE_PLUGIN_ROOT}/snippets/git-scale-protocol.md`.

PR title + body follow `${CLAUDE_PLUGIN_ROOT}/snippets/commit-convention.md` (business subject,
72-char ceiling).

## Issue triage

| Step | MCP | gh |
|---|---|---|
| Read | `issue_read` | `gh issue view <n>` |
| List / search | `list_issues` / `search_issues` | `gh issue list` / `gh search issues` |
| Create / update | `issue_write` | `gh issue create` / `gh issue edit` |
| Comment | `add_issue_comment` | `gh issue comment <n>` |
| Sub-issue link | `sub_issue_write` | (no equivalent) |

## Search

`search_code`, `search_repositories`, `search_pull_requests`, `search_commits` -
MCP-primary. gh: `gh search code/repos/prs/commits`.

## Releases

```bash
# MCP read: list_releases / get_latest_release / get_release_by_tag
gh release create v1.2.3 --title "v1.2.3" --notes-file NOTES.md   # create (no MCP equivalent)
gh release list
```

Tag a release annotated:

```bash
git tag -a v1.2.3 -m "Release v1.2.3" && git push origin v1.2.3
```

## CI status (gh - script-safe exit codes)

```bash
gh pr checks <n>
gh run list --limit 5
gh run view <run-id> --log-failed     # only failed step logs
```

## Fork -> PR upstream

```bash
# MCP: fork_repository
gh pr create --repo <upstream-owner>/<repo> --base <branch> \
  --head <your-user>:<your-branch> --title "..." --body-file BODY.md
```

## DCO on a pushed range

```bash
git rebase --signoff <base>     # add Signed-off-by to each commit, then force-with-lease push
```
