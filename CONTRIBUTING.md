# Contributing to Odoo MCP Client

Thanks for your interest! This repo is the **MIT client layer**, published as **two
plugins** under `plugins/`: `odoo-ai-agents` (skills, agents, workflow commands,
the SSOT generator, and IDE snippets) and `odoo-semantic-mcp` (the MCP server connection
plus the `/odoo-semantic-mcp:connect` setup command). The semantic backend lives in the
separate AGPL server; open server/indexer/graph issues via
[odoo-semantic.viindoo.com](https://odoo-semantic.viindoo.com/).

## Local development

**Prerequisite:** Python 3.12 or newer must be on your PATH.

```bash
git clone https://github.com/Viindoo/odoo-mcp-client
cd odoo-mcp-client

# One-time setup: create .venv and install dependencies from requirements.txt:
make setup

# Load a plugin from this checkout (no marketplace round-trip):
claude --plugin-dir ./plugins/odoo-ai-agents   # or ./plugins/odoo-semantic-mcp

# Validate manifest + skill frontmatter + run the test suite:
make validate
make test
```

> `make setup` creates `.venv/` and installs all test dependencies. `make test` and
> `make validate` both use `.venv` automatically; if you skip `make setup`, the first
> `make test` run will bootstrap the venv for you.

You also need a running MCP server to exercise the tools end-to-end - point
`/odoo-semantic-mcp:connect` at the hosted instance (`https://odoo-semantic.viindoo.com/mcp`).
Use the hosted instance at https://odoo-semantic.viindoo.com/install/ (sign up for an API key).

### Pre-commit hooks

Before pushing, install the confidentiality pre-commit hook to catch Viindoo-internal data
leaks (vault paths, personal email, absolute `~/.` paths):

```bash
git config --local core.hooksPath .githooks/
```

The hook blocks hard-fail patterns (vault path, personal email) and issues warnings for
sensitive numeric values (pricing/OKR figures). Run `make validate && make test` as well.

### Running tests locally

Run the full quality gate locally before pushing - the same steps that CI runs. This is
how to avoid the version-drift and generated-artifact failures that block PRs.

**1. Create the venv (one time per checkout)**

`make setup` bootstraps `.venv/` and installs all test dependencies from `requirements.txt`:

```bash
make setup
```

If you prefer `uv` (faster, no ensurepip dependency):

```bash
uv venv .venv --python 3.12
uv pip install -r requirements.txt
touch .venv/.stamp   # let Makefile targets reuse this venv
```

`.venv/` is gitignored and must never be staged.

**2. Run the full gate**

```bash
make validate    # plugin schema check + tests/test_plugin_schema.py + test_skill_format.py + workflow schema
make test        # full pytest suite (tests/) - same command CI runs
make gen-check   # regenerate SSOT artifacts, then fail if any diff remains
```

What each gate enforces:

| Command | What it catches |
|---|---|
| `make validate` | Malformed plugin.json, bad skill frontmatter, description over 1024 chars, workflow schema violations |
| `make test` | All pytest tests including `test_version_consistency.py` (VERSION == plugin.json), naming rules, routing-sync checks, disambiguation contract |
| `make gen-check` | Generated artifacts (gemini-extension.json, skill `## MCP tools` sections, IDE snippets, orchestration map) not committed after a change to their SSOT |

Run all three together before every push:

```bash
make validate && make test && make gen-check
```

**3. Never hand-edit version fields - always use the bump script**

The repo tracks `VERSION` (root), `plugins/odoo-ai-agents/.claude-plugin/plugin.json`,
`plugins/odoo-ai-agents/.codex-plugin/plugin.json`, and `gemini-extension.json` as a
lockstep set. Editing any of them by hand will cause `tests/test_version_consistency.py`
to fail in CI, and the gemini manifest to drift (caught by `make gen-check`).

Always bump via the script, which updates all four atomically and cuts the CHANGELOG:

```bash
# Level policy: patch = fix/refactor/docs, minor = new feature/skill/agent/command, major = breaking
scripts/bump-version.sh minor    # or patch / major / an explicit X.Y.Z
# Preview without writing:
make bump-dry
```

After bumping, run `make gen` to regenerate all version-derived artifacts, then `make gen-check`
to confirm zero drift, then check the CHANGELOG `## [x.y.z]` section looks right before committing.

**4. Sign every commit (DCO)**

Every commit must carry a `Signed-off-by:` trailer - see [DCO](#developer-certificate-of-origin-dco)
below. Use `git commit -s` (the `-s` flag appends the trailer automatically). PRs without
signed commits will be asked to amend before merge.

## What lives where

| Path | Contents |
|------|----------|
| `plugins/odoo-ai-agents/.claude-plugin/plugin.json` | Skills plugin manifest (skills/agents/commands; declares `odoo-semantic-mcp` as a dependency) |
| `plugins/odoo-ai-agents/skills/<name>/SKILL.md` | One skill per directory, YAML frontmatter + body |
| `plugins/odoo-ai-agents/agents/*.md` | Orchestration agents |
| `plugins/odoo-ai-agents/commands/*.md` | Workflow slash commands |
| `plugins/odoo-ai-agents/.mcp.json` | Bundled browser MCP servers (`chrome-devtools`, `playwright`, `pagecast`) loaded with the plugin for the visual stack |
| `plugins/odoo-ai-agents/hooks/` | Plugin lifecycle hooks (`hooks.json` + scripts) - e.g. the SessionStart visual-stack readiness probe |
| `plugins/odoo-ai-agents/scripts/lib/` | Shared bash/python setup utilities (`config_merge.py`, `discover_odoo.sh`) reused by setup steps |
| `plugins/odoo-ai-agents/scripts/setup-steps/` | Numbered, idempotent setup steps (`describe \| check \| apply`) driven by `/odoo-ai-agents:odoo-setup` |
| `plugins/odoo-ai-agents/generator/` | SSOT generator (`gen_surface.py`) + server-surface inputs |
| `plugins/odoo-ai-agents/snippets/` | MCP config for non-Claude clients, plus agent-facing SSOT protocol snippets (disk-fallback-protocol, context-bootstrap, osm-first-contract, nesting-guard) referenced by skill/agent bodies |
| `plugins/odoo-ai-agents/docs/` | Persona guides, client setup, orchestration map + reference docs |
| `plugins/odoo-semantic-mcp/.claude-plugin/plugin.json` | MCP plugin manifest (userConfig for URL + API key) |
| `plugins/odoo-semantic-mcp/.mcp.json` | MCP server template (resolved from `userConfig`) |
| `plugins/odoo-semantic-mcp/commands/connect.md` | The `/odoo-semantic-mcp:connect` slash command |

### Naming policy: `odoo-semantic` and its variants

This repo grew out of a single plugin once called `odoo-semantic`, later split into two
plugins. To keep docs unambiguous for both humans and AI agents, always pick the form that
matches what you actually mean:

| You mean… | Write exactly | Where it appears |
|-----------|---------------|------------------|
| The plugin that ships the MCP server connection + connect command | `odoo-semantic-mcp` | Plugin name, `/odoo-semantic-mcp:connect`, dependency declarations |
| The plugin that ships the skills / agents / commands | `odoo-ai-agents` | Plugin name, `/odoo-ai-agents:odoo-setup`, etc. |
| The product / brand / hosted service | `Odoo Semantic` (prose) or `OSM` (abbrev) | README prose, "the Odoo Semantic service"; URL `odoo-semantic.viindoo.com` |
| The **MCP server id** (runtime identifier) | `odoo-semantic` in backticks, config/code only | `.mcp.json`, editor snippets - naming the registered server id. NEVER as a plugin name |
| The **tool-call prefix** | `mcp__odoo-semantic__*` | Tool names in skills/agents/docs/tests - always the full `mcp__…__` form |
| The running MCP server, as a noun in prose | `the odoo-semantic-mcp server` | Fallback / standalone sections ("when the … server is unreachable") |

Rule of thumb: a bare `odoo-semantic` token that is **not** inside `mcp__…__`, **not** a
config server-id field, **not** part of a URL, and **not** the brand words "Odoo Semantic" /
"OSM" is suspect - it should usually carry a `-mcp` / `-skills` suffix or be rephrased.
`tests/test_naming_consistency.py` enforces this on the skill / command / trigger-phrase
surface; historical entries in `CHANGELOG.md` are intentionally exempt.

### Agent-facing prose: version-agnostic & capability-described

The `disambiguation` block in `generator/server-surface.json` (and anything else AI clients
read to route - snippets, SKILL.md `## MCP tools` sections) must be:

- **Version-agnostic** - never hardcode a version range (`v8-v19`) or count. A new Odoo
  release would silently make it wrong and no test catches stale prose. Use
  "every indexed Odoo version", "cross-version", "legacy through latest". Need a concrete
  list for a user? Read it at runtime via `list_available_versions`, don't bake it in.
- **Capability-described, not product-named** - refer to other tools by capability
  ("a live Odoo MCP server exposing `read_record`/`search_records`/`execute_method`"),
  not a specific third-party product name, so it survives ecosystem churn.
- **No machine/deployment data** - never embed a specific instance's host/db/path/user/key
  (this repo is public).

The block must also carry the **OSM-first precedence**, and must NOT get it backwards:
Odoo Semantic is the **PRIMARY**, context-efficient source for Odoo source/structure - the
Odoo codebase is huge and reading it directly burns context. Reading code (Read/Grep) is the
**FALLBACK**, only when OSM is reachable-but-incomplete or unavailable - never the first move
when OSM can answer. Do NOT tell agents to prefer their own file tools over OSM for a local
checkout (an earlier draft did; it inverts the intended flow).

Why: AI agents otherwise silently mis-route - calling a live-instance Odoo MCP (wrong: OSM is
STATIC), or skipping OSM to read the codebase (wrong: that is the fallback). The prose must
assert a unique signature (indexed, cross-version, inheritance-resolved, checkout-free), the
OSM-first precedence, and the live-data boundary. This mirrors the server-side `INSTRUCTIONS`
SSOT in [Viindoo/odoo-semantic-server](https://github.com/Viindoo/odoo-semantic-server)
(`src/mcp/server.py`); keep the two in sync. Guard: `tests/test_disambiguation.py`.

### Skill format

Each `plugins/odoo-ai-agents/skills/<name>/SKILL.md` must start with YAML frontmatter containing at least a
`name` and a `description`. The description is what drives routing - keep it specific and
trigger-rich, but **under 1024 characters**: Claude truncates longer descriptions out of the
skill listing, which silently degrades triggering. Trim duplicate trigger phrases and
illustrative examples before cutting any `route to …` / `DO NOT trigger → …` disambiguation
clause. `make test` enforces all of this via `tests/test_skill_format.py` (frontmatter
shape), `tests/test_skill_description_budget.py` (the 1024-char cap), and
`tests/test_odoo_intake_quote_sync.py` (every skill/workflow the `odoo-intake` router points at must
exist).

### Agent format

Each `plugins/*/agents/<name>.md` is **YAML frontmatter + a Markdown body**, and the two halves
have distinct readers - keep their content separate:

- **Frontmatter** carries `name`, `description`, `model` (and optional `color` / `tools`). The
  `description` is **routing metadata**: it tells the orchestrator *when to delegate* to this
  agent (triggers, `<example>` scenarios, "use this agent when …"). It is read at routing time,
  by the caller deciding whether to dispatch - not by the running agent.
- **Body** is the agent's **system prompt**: role + operating procedure + constraints + output
  contract, written in the second person ("You are …"). It is read by the running agent at
  startup, so it must contain only what the agent needs to *do the work* - never how a caller
  decides to pick it.

Do **not** add a `## When to invoke` / "when to use me" routing section to the body: it
duplicates the `description` and pollutes the system prompt with text the running agent cannot
act on. Genuine runtime constraints (read-only, one SHA per instance, never spawn subagents)
belong in the role intro or a dedicated constraints section of the body, not in a routing
heading. Worked "when to dispatch" scenarios belong in the `description` (inline or as
`<example>` blocks). Guard: `tests/test_agent_body_convention.py`.

This mirrors Anthropic's subagent contract - the frontmatter `description` is the selection
signal and the body is the system prompt: see
[Subagents](https://code.claude.com/docs/en/sub-agents) and the Agent SDK
[Subagents](https://docs.claude.com/en/api/agent-sdk/subagents) reference.

### Naming convention: skill vs agent vs command (morphology)

Names encode **role**, so an AI router (and a human) can tell the three layers apart even
when a name appears bare - without its `odoo-ai-agents:` namespace - in a cross-reference
or in the model's own reasoning. The rule:

- **Skill** = a **capability noun** - either a noun phrase (`-review`, `-analysis`, `-diff`,
  `-audit`, `-proof`, `-overview`) or a gerund (`-coding`, `-recording`, `-handling`). It names
  *what competence is offered*. **Never** an agent suffix (`-er/-or/-ist/-finder/-handler`) and
  **never** a bare imperative verb (`summarize`, `onboard`).
- **Agent** = an **agent-of-action noun** with an actor suffix (`-er/-or/-ist`): `odoo-coder`,
  `odoo-code-reviewer`. It names *the executor that does the work*.
- **Command** = an **imperative verb-object** phrase: `odoo-run-brl`, `odoo-plan-upgrade`,
  `odoo-draft-followup`. Lead with the verb; keep an object so it never collides with the
  verb-space a skill uses to trigger. The frontmatter `name` **must equal the filename** (that
  is the invoked name; `name` is only a display label).
- **Prefix `odoo-`** on every Odoo-specific skill/agent/command. `odoo-intake` follows this
  convention like every other skill; the bare `intake` namespace is reserved for a future
  domain-agnostic front door (one that may invoke `odoo-intake` when it detects Odoo intent).
  The two remaining unprefixed names are the domain-agnostic mechanisms: `wave`,
  `workflow-chaining`.

A skill that dispatches an agent pairs a capability with an actor: skill `odoo-code-review`
dispatches agent `odoo-code-reviewer`; skill `odoo-backend-coding` dispatches agent
`odoo-coder`. The names must differ (capability vs actor) - identical skill==agent names are a
violation, because a bare reference can no longer say which layer it means.

## Pull requests

1. Fork and branch from `master`.
2. Keep changes scoped; one logical change per PR.
3. Run `make validate && make test` before pushing.
4. Fill in the PR template.
5. **Sign off your commits** (DCO - see below).

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
opens an auto-merge PR on the marketplace repo pinning both split plugins' `source.sha`
(`odoo-ai-agents` and `odoo-semantic-mcp`) to the new commit.

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

`VERSION` is the single source of truth for the client version. The repo ships **two
plugins** with independent version numbers: the `odoo-ai-agents` plugin's
`plugin.json.version` is kept in lockstep with `VERSION`, while the
`odoo-semantic-mcp` plugin versions independently. Tagging `v*`
should bump `VERSION` together with the skills plugin's `plugin.json.version`; bump the
mcp plugin's version only when its own contents change. `pin-sha.yml` updates `source.sha`
for both plugins on every qualifying push; each marketplace entry's `source.version`
tracks its respective `plugin.json.version`.

**Bumping.** Prefer `make bump`, which **auto-classifies** the level from the commits
since `VERSION` last changed and then bumps. It updates `VERSION`, the `odoo-ai-agents`
`plugin.json.version`, and cuts the `## [Unreleased]` CHANGELOG block to `## [x.y.z] - DATE`
in one step - so the version and changelog never drift apart. Run `make bump-dry` to preview
the suggested level + resulting version without writing anything.

**How the level is decided (this is the operational policy - apply it, don't default to minor):**

- **patch** (3rd number) - bug fixes / internal refactors / docs / chore / test. **This is the
  default** for any change that is not a new feature or a break. Do not skip it: a fix-only
  release is a patch, not a minor.
- **minor** (2nd number) - a backward-compatible feature, **including a new command, skill, or
  agent**, or any `feat:` commit.
- **major** (1st number) - a breaking change (a `type!:` commit or a `BREAKING CHANGE:` note).

`make bump` reads this from git deterministically: it anchors on the commit that last touched
`VERSION` (the `v*` tags lag `VERSION` and are **not** used as the anchor) and inspects the
commit subjects/bodies and newly added files in that range. A `feat:` commit or a new file under
`skills/`, `agents/`, or `commands/` → **minor**; a `type!:`/`BREAKING CHANGE:` → **major**;
otherwise → **patch**.

**In an AI session, honor a natural-language version request.** If the human names a specific
version or level ("bump to 3.11.0", "this is a patch", "minor please"), the agent runs the
explicit form - `scripts/bump-version.sh 3.11.0` or `scripts/bump-version.sh patch` - which
takes precedence over auto-classification. Otherwise the agent runs `make bump` (i.e.
`scripts/bump-version.sh auto`) and **confirms the suggested level** (e.g. via `make bump-dry`)
before applying.

The manual targets remain for when you want to force a level: `make bump-patch` / `make bump-minor`
/ `make bump-major` (or `scripts/bump-version.sh <level>`). `tests/test_version_consistency.py`
fails CI if `VERSION` and the skills `plugin.json.version` ever diverge, or if `VERSION` is not
valid `MAJOR.MINOR.PATCH`.

### Rollback runbook

If a release breaks installs after the marketplace PR merges:

1. **Revert the marketplace pin** - open a one-line PR on `Viindoo/claude-plugins`
   resetting `source.sha` (and `source.url` if it changed) to the last-known-good commit,
   or edit `marketplace.json` directly.
2. Existing users are unaffected until they `claude plugin update`; the revert restores
   the good SHA for everyone.
3. If a bad commit must be pulled entirely, fix forward on `master` here - a new
   qualifying push re-pins automatically.
4. As a last resort, bump `VERSION` (e.g. `2.0.1-revert`) and announce via the usual
   channel.

**Automated kill-switch:** For proactive blocking, add the bad commit's 7-char short SHA to
[`BLOCKED_VERSIONS.md`](BLOCKED_VERSIONS.md). The `pin-sha.yml` workflow will detect the
entry and skip the marketplace pin step automatically, without failing the CI run.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
