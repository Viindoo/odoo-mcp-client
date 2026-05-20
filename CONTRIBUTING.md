# Contributing to Odoo MCP Client

Thanks for your interest! This repo is the **MIT client layer** — plugin manifest,
skills, agents, the connect command, and IDE snippets. The semantic backend lives in
the separate AGPL [odoo-semantic-mcp](https://github.com/Viindoo/odoo-semantic-mcp)
repo; open server/indexer/graph issues there.

## Local development

```bash
git clone https://github.com/Viindoo/odoo-mcp-client
cd odoo-mcp-client

# Load the plugin from this checkout (no marketplace round-trip):
claude --plugin-dir ./

# Validate manifest + skill frontmatter + run the test suite:
make validate
make test
```

You also need a running MCP server to exercise the tools end-to-end — point
`/odoo-semantic:connect` at the hosted instance (`https://odoo-semantic.viindoo.com/mcp`)
or a [self-hosted server](https://github.com/Viindoo/odoo-semantic-mcp).

## What lives where

| Path | Contents |
|------|----------|
| `.claude-plugin/plugin.json` | Plugin manifest (skills/agents/commands/userConfig) |
| `.mcp.json` | MCP server template (resolved from `userConfig`) |
| `skills/<name>/SKILL.md` | One skill per directory, YAML frontmatter + body |
| `agents/*.md` | Orchestration agents |
| `commands/connect.md` | The `/odoo-semantic:connect` slash command |
| `snippets/` | MCP config for non-Claude clients |
| `docs/` | Persona guides, client setup, tool routing reference |

### Skill format

Each `skills/<name>/SKILL.md` must start with YAML frontmatter containing at least a
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

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
