# Contributing to Odoo MCP Client

Thanks for your interest! This repo is the **MIT client layer**, published as **two
plugins** under `plugins/`: `odoo-semantic-skills` (skills, agents, workflow commands,
the SSOT generator, and IDE snippets) and `odoo-semantic-mcp` (the MCP server connection
plus the `/odoo-semantic-mcp:connect` setup command). The semantic backend lives in the
separate AGPL server; open server/indexer/graph issues via
[odoo-semantic.viindoo.com](https://odoo-semantic.viindoo.com/).

## Local development

```bash
git clone https://github.com/Viindoo/odoo-mcp-client
cd odoo-mcp-client

# Load a plugin from this checkout (no marketplace round-trip):
claude --plugin-dir ./plugins/odoo-semantic-skills   # or ./plugins/odoo-semantic-mcp

# Validate manifest + skill frontmatter + run the test suite:
make validate
make test
```

You also need a running MCP server to exercise the tools end-to-end — point
`/odoo-semantic-mcp:connect` at the hosted instance (`https://odoo-semantic.viindoo.com/mcp`).
Use the hosted instance at https://odoo-semantic.viindoo.com/ (sign up for an API key).

### Pre-commit hooks

Before pushing, install the confidentiality pre-commit hook to catch Viindoo-internal data
leaks (vault paths, personal email, absolute `~/.` paths):

```bash
git config --local core.hooksPath .githooks/
```

The hook blocks hard-fail patterns (vault path, personal email) and issues warnings for
sensitive numeric values (pricing/OKR figures). Run `make validate && make test` as well.

## What lives where

| Path | Contents |
|------|----------|
| `plugins/odoo-semantic-skills/.claude-plugin/plugin.json` | Skills plugin manifest (skills/agents/commands; declares `odoo-semantic-mcp` as a dependency) |
| `plugins/odoo-semantic-skills/skills/<name>/SKILL.md` | One skill per directory, YAML frontmatter + body |
| `plugins/odoo-semantic-skills/agents/*.md` | Orchestration agents |
| `plugins/odoo-semantic-skills/commands/*.md` | Workflow slash commands |
| `plugins/odoo-semantic-skills/generator/` | SSOT generator (`gen_surface.py`) + server-surface inputs |
| `plugins/odoo-semantic-skills/snippets/` | MCP config for non-Claude clients |
| `plugins/odoo-semantic-skills/docs/` | Persona guides, client setup, tool routing reference |
| `plugins/odoo-semantic-mcp/.claude-plugin/plugin.json` | MCP plugin manifest (userConfig for URL + API key) |
| `plugins/odoo-semantic-mcp/.mcp.json` | MCP server template (resolved from `userConfig`) |
| `plugins/odoo-semantic-mcp/commands/connect.md` | The `/odoo-semantic-mcp:connect` slash command |

### Skill format

Each `plugins/odoo-semantic-skills/skills/<name>/SKILL.md` must start with YAML frontmatter containing at least a
`name` and a `description`. The description is what drives routing — keep it specific and
trigger-rich. `make test` runs `tests/test_skill_format.py` to enforce this.

## Pull requests

1. Fork and branch from `master`.
2. Keep changes scoped; one logical change per PR.
3. Run `make validate && make test` before pushing.
4. Fill in the PR template.
5. **Sign off your commits** (DCO — see below).

### Developer Certificate of Origin (DCO)

By contributing you certify the [DCO 1.1](https://developercertificate.org/). Add a
sign-off line to every commit:

```bash
git commit -s -m "your message"
```

This appends `Signed-off-by: Your Name <you@example.com>`. PRs whose commits lack a
sign-off will be asked to amend.

## Release & marketplace pipeline (maintainers)

The plugin is published through the `Viindoo/claude-plugins` marketplace. A push to
`master` that touches plugin content triggers `.github/workflows/pin-sha.yml`, which
opens an auto-merge PR on the marketplace repo pinning `source.sha` to the new commit.

### Required secret: `CLAUDE_PLUGINS_PAT`

`pin-sha.yml` needs write access to `Viindoo/claude-plugins`. Configure a repository
secret named `CLAUDE_PLUGINS_PAT`:

1. Prefer a **fine-grained PAT** scoped to `Viindoo/claude-plugins` with
   `Contents: read & write` and `Pull requests: read & write`.
2. If a fine-grained PAT cannot target an org repo in your setup, fall back to a
   **classic PAT** with the `repo` scope.
3. Add it under **Settings → Secrets and variables → Actions → New repository secret**.
4. Optional: set `SLACK_WEBHOOK_URL` so workflow failures post to your channel.

**Rotation:** rotate `CLAUDE_PLUGINS_PAT` every **90 days** (set the PAT expiry to match
and put a calendar reminder on it). A leaked token only grants write to the marketplace
repo, but rotate immediately if exposure is suspected.

### Versioning

`VERSION` is the single source of truth for the client version. Tagging `v*` should bump
`VERSION` and `plugin.json.version` together. `pin-sha.yml` updates `source.sha` on every
qualifying push; the marketplace `source.version` tracks `VERSION`.

### Rollback runbook

If a release breaks installs after the marketplace PR merges:

1. **Revert the marketplace pin** — open a one-line PR on `Viindoo/claude-plugins`
   resetting `source.sha` (and `source.url` if it changed) to the last-known-good commit,
   or edit `marketplace.json` directly.
2. Existing users are unaffected until they `claude plugin update`; the revert restores
   the good SHA for everyone.
3. If a bad commit must be pulled entirely, fix forward on `master` here — a new
   qualifying push re-pins automatically.
4. As a last resort, bump `VERSION` (e.g. `0.5.1-revert`) and announce via the usual
   channel.

**Automated kill-switch:** For proactive blocking, add the bad commit's 7-char short SHA to
[`BLOCKED_VERSIONS.md`](BLOCKED_VERSIONS.md). The `pin-sha.yml` workflow will detect the
entry and skip the marketplace pin step automatically, without failing the CI run.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
