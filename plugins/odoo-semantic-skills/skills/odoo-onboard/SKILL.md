---
name: odoo-onboard
description: |
  Bootstrap Odoo project context on first use — probe the Odoo environment (version, custom modules, active profile, naming conventions) and persist findings to `.odoo-ai/context.md` at project root (gitignored), so every later `odoo-*` skill reads it as Round -1 and skips setup.

  Trigger AGGRESSIVELY on "new Odoo project" / "first time" signals, or when no `.odoo-ai/context.md` exists yet: "set up Odoo for this project", "initialize Odoo context". Also fires on Vietnamese: "khởi tạo dự án Odoo mới", "thiết lập context Odoo". Implicit: dir has `__manifest__.py` but no `.odoo-ai/context.md` → first `odoo-*` skill recommends onboard; intake also escalates here when context is missing.

  DO NOT trigger when: (1) `.odoo-ai/context.md` exists and `last_updated` < 30 days — offer "refresh?" instead; (2) no `__manifest__.py` within 3 levels; (3) the user is mid-workflow inside another skill (e.g. odoo-coder writing code) — don't interrupt; (4) the user types another skill's trigger — let that skill fire
---

# Odoo Onboard — Project Context Bootstrap

## Persona

Front door for **all Odoo personas** (small-team founder, Developer, Pre-Sales Consultant, Sales AE, Marketer, Strategist, Customer Success). Most useful on the FIRST session against a new Odoo project repo — once context exists, the user rarely runs onboard again (only on quarterly refresh or major version change).

## Out of Scope

- **NEVER write outside `.odoo-ai/`.** No edits to Odoo source files, no edits to manifest files, no changes to project structure. The skill writes one context file + one `.gitignore` line.
- **NEVER call MCP write tools** (no `create_*` / `update_*` / `import_*`). Only read tools: `list_available_versions`, `list_available_profiles`, `set_active_version`, `set_active_profile`, `check_module_exists`.
- **NEVER assume context without user confirm.** Every detected field (version, profile, module list, prefix) must be shown to the user and confirmed before persisting. Detection is a suggestion, not a fact.
- **NEVER overwrite an existing recent context.** If `.odoo-ai/context.md` exists and `last_updated` < 30 days, ask before overwriting.
- **NEVER probe outside the working directory.** Limit `find` and `grep` to the current working directory + 3 levels deep, to avoid touching unrelated repos on the same machine.

## Onboarding workflow

The skill follows 9 steps. Each step has a clear success criterion before moving to the next.

### Step 0 — Pre-flight

Check `.odoo-ai/context.md` existence:
- If exists AND `last_updated` < 30 days → output: "Context already exists (updated <date>). Refresh? (yes/no)". On "no", end the skill. On "yes", continue but preserve the user's existing `## Notes` section AND the `## Instance / Visual` section (written by `/odoo-semantic-skills:setup`, not re-derivable by onboard).
- If exists AND stale (>30 days) → say so + continue with refresh.
- If absent → continue.

### Step 1 — Detect project root

```bash
find . -maxdepth 3 -name "__manifest__.py" 2>/dev/null | head -20
```

- If 0 results → output: "No `__manifest__.py` found in working dir. Is this an Odoo repo? If so, provide the project root path." Wait for user input.
- If ≥1 results → infer project root (common parent of all manifest paths) → continue.

### Step 2 — Probe available Odoo versions

Call `mcp__odoo-semantic__list_available_versions` (no args). Show user the list with the most likely default highlighted (heuristic: prefer 17.0 if listed; otherwise highest version).

> "Available versions: 8.0, 12.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0. Which version does this project target? (default: 17.0)"

Wait for user pick. Validate it's in the available list.

### Step 3 — Probe available profiles

Call `mcp__odoo-semantic__list_available_profiles` (no args). Show with default heuristic:
- Pure Odoo project (no `viin_*` module prefix in Step 4) → default profile = `odoo_<version>` or null
- Custom distribution project (≥1 `viin_*` module) → default profile = `viindoo_internal_<version>`

> "Which profile? Detected `<inferred>` based on modules. (yes / pick another)"

Wait for user pick.

Once the profile is chosen, call `mcp__odoo-semantic__profile_inspect(method='summary', name=<chosen_profile>, odoo_version=<chosen_version>)` to capture its real composition — inheritance chain, repos, and the indexed module count — and record it into `.odoo-ai/context.md` (e.g. a `viindoo_profile_modules: <count>` line). Downstream skills then inherit the real inventory instead of re-deriving it, and this doubles as validation that the picked profile name actually resolves (a hyphenated or unversioned name returns nothing).

### Step 4 — Discover custom modules

```bash
find . -maxdepth 3 -name "__manifest__.py" -exec dirname {} \; | head -50
```

For each path, extract module name (basename of dir) + read `__manifest__.py` to grep `'summary':` value (1-line).

Build a list:
```
1. viin_sale_advance — "Sale order advance payments for Viindoo"
2. viin_account_vat — "Vietnam VAT compliance"
3. custom_loyalty — "Customer loyalty program"
... (N total)
```

Show to user:
> "Detected `<N>` modules in this repo. Include all? Or edit list? (yes / list to exclude)"

Wait for user pick. If user wants to exclude, prompt for line numbers or names.

### Step 5 — Extract team conventions

From the confirmed module list, detect:
- **module_prefix**: longest common prefix across module names (e.g., `viin_` appears in 8/10 modules → prefix is `viin_`). If multiple competing prefixes, report top-2.
- **field_naming**: assume `snake_case` (Odoo standard). Override only if user says otherwise.
- **vcs_branch_pattern**: optional — try `git log --oneline -20 | head -20` to detect branch naming heuristic (`feature/...`, `fix/...`, `OEEL-<N>-...`). Don't probe if not in git repo.

Also detect lint/format provenance for downstream skills (especially the frontend verify gate):

**Python linter (ruff) line-length:**
```bash
# Check pyproject.toml first, then ruff.toml
grep -m1 'line-length' pyproject.toml ruff.toml 2>/dev/null | head -1
```
- If a `line-length` value is found (e.g. `line-length = 120`), record it as-is.
- If absent (Odoo core has no ruff line-length; v19 ruff.toml ignores E501), record `"none"`.
- Never assume a default — Odoo core sets no ruff line-length, while some projects pin one (e.g. 120). Read the value from the project config; do not guess.

**JS formatter/linter config:**
```bash
# Check for Odoo checkout with committed web tooling (present v15+)
find . "${ODOO_GIT_BASE:-$HOME/git}" -maxdepth 6 -path "*/addons/web/tooling" -type d 2>/dev/null | head -1
```
- If `addons/web/tooling/` is locatable (an Odoo checkout with committed eslint/prettier config, available from v15+), record `"web/tooling"`.
- Otherwise record `"fallback"` (the plugin's `scripts/odoo-prettierrc.json` will be used: tabWidth 4, printWidth 100).

Confirm with user in one batch:
> "Conventions: prefix=`viin_`, field=`snake_case`, branch=`feature/<ticket>-<slug>`. Lint: ruff line-length=`120`, JS=`web/tooling`. Correct? (yes / edit)"

### Step 6 — Set session pins

Call `mcp__odoo-semantic__set_active_version` with `odoo_version=<from Step 2>`.
Call `mcp__odoo-semantic__set_active_profile` with `profile=<from Step 3>` (skip if null).

Capture confirmation messages. If either call fails, log the error in context file under `## Notes` and continue.

### Step 7 — Write context file

Create `.odoo-ai/` directory if absent:
```bash
mkdir -p .odoo-ai
```

Write `.odoo-ai/context.md` per the schema below. If refreshing, preserve the user's `## Notes` section verbatim AND the `## Instance / Visual` section verbatim (onboard does not own those keys — `/odoo-semantic-skills:setup` writes the instance/visual config and the user owns notes).

### Step 8 — Update `.gitignore`

- If `.gitignore` exists → grep for `.odoo-ai/`; if not present, append `.odoo-ai/` (with leading newline if file doesn't end in one). If present, no-op (idempotent).
- If `.gitignore` absent → create with single line `.odoo-ai/`.

### Step 9 — Verify + suggest next

Read back `.odoo-ai/context.md`, show user the summary block (per Output Format below). Ask:

> "Anything to add to `## Notes` section? (text / skip)"

If user provides notes, append to `## Notes` section. Then output the suggest-next line.

## Context file schema

```markdown
# Odoo Project Context

> Generated by `odoo-onboard` skill on <ISO8601>. Read by all `odoo-*` skills as Round -1 (before Round 0: `set_active_version`).

## Environment
- **odoo_version**: 17.0
- **viindoo_profile**: viindoo_17  (or `null` if pure Odoo)
- **edition**: your Odoo distribution  (one of: CE | EE | custom)

## Custom modules detected
- viin_sale_advance — Sale order advance payments
- viin_account_vat — Vietnam VAT compliance
- custom_loyalty — Customer loyalty program

## Team conventions
- **module_prefix**: viin_
- **field_naming**: snake_case
- **vcs_branch_pattern**: feature/<ticket-id>-<slug>

## Lint / Format
- **ruff_line_length**: 120  (read from pyproject.toml/ruff.toml; "none" if absent)
- **js_config_source**: web/tooling  (or "fallback" when no Odoo checkout with addons/web/tooling/ is locatable)

## Active session pins
- **set_active_version**: 17.0 (TTL 24h — re-pin if stale)
- **set_active_profile**: viindoo_17

## Instance / Visual  (optional — populated by /odoo-semantic-skills:setup)
- **instance_base_url**: http://localhost:8069
- **instance_login**: admin  (password NEVER stored here — agreed credential source only)
- **visual_mcp**: chrome-devtools  (the browser MCP wired for the visual skills)
- **screenshot_baseline_dir**: .odoo-ai/visual/baseline
- **brand_tokens_source**: .odoo-ai/brand-tokens.json  (optional — consumer-declared JSON map `token -> color`, e.g. `{"--primary": "#1E88E5"}`; enables the brand-fidelity checks in verify-frontend.sh Tier 4 + ui-reviewer Step 4b. Omit for pure-Odoo projects. No brand is vendored in the plugin.)
- **mockup_dir**: .odoo-ai/mockups  (optional — reference mockups/design specs for the mockup-first fidelity check)

## last_updated
2026-05-28T11:30:00Z

## Notes
<user-provided free-form notes, preserved across refresh>
```

Fields are markdown bullets (not YAML) so the file is human-readable + diff-friendly. Downstream skills parse via regex `^\s*-\s*\*\*<key>\*\*:\s*(.+)$`.

## Output format

After Step 9, output exactly this template:

```
✓ Onboarding complete

**Project context** saved to `.odoo-ai/context.md`:
- Odoo version: <X.0>
- Profile: <name or "(none)">
- Modules detected: <N> (top: <m1>, <m2>, <m3>)
- Module prefix: <prefix>
- Lint: ruff line-length=<value or "none">, JS=<"web/tooling" or "fallback">

`.gitignore` updated to exclude `.odoo-ai/`.

Suggest next: <relevant follow-up — see "Suggest-next logic" below>
```

### Suggest-next logic

Pick ONE based on detected context:
- If many `viin_*` modules + custom distribution profile → "Run `odoo-customization-inventory` to list all modules and assess business purpose."
- If user mentioned "upgrade" or "migration" in original prompt → "Run `odoo-deprecation-audit` next."
- If user mentioned "feature" or "client" → "Try `odoo-feature-check` or `odoo-gap-analysis`."
- If the repo has frontend assets (`static/src/js`, `*.scss`, OWL/QWeb templates) OR the user mentioned UI / giao diện / demo / video → "Run `/odoo-semantic-skills:setup` to wire the visual stack (browser MCP + instance URL), so `odoo-ui-reviewer`, `odoo-ui-debug`, `odoo-visual-regression`, and `odoo-demo-recorder` can drive a live instance."
- Default → "Ready for any `odoo-*` skill. All skills will auto-read `.odoo-ai/context.md` from Phase B onwards."

## Standalone-first fallback

When OSM (the `odoo-semantic-mcp` server) is unreachable: still auto-discover modules
via the disk probes in Steps 1 and 4 (`find . -maxdepth 3 -name "__manifest__.py"`; read
each manifest). For Odoo version, attempt to read the `version` field from any discovered
manifest (first two dotted components) or check `pyproject.toml` / `setup.cfg` for an
Odoo version pin before asking the user. Only ask the user for the version if it cannot
be inferred from any on-disk source. The skill still creates `.odoo-ai/context.md` with
flag `osm_verified: false` so downstream skills know the context is user-asserted (not
index-verified).

## Integration notes

- **Phase A/B (current)**: Onboard writes `.odoo-ai/context.md`. Many `odoo-*` skills
  now include a Round 0 context bootstrap (via
  `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md`) that reads this file to
  pre-fill `odoo_version`, `viindoo_profile`, and module list - skipping those questions
  entirely. Skills updated to Round 0: `odoo-gap-analysis`, `odoo-support-triage`,
  `odoo-qa-suite`, `odoo-risk-overview`, `odoo-customization-inventory`, and others
  following the same snippet pattern. The file is forward-compatible - its presence does
  not break skills that do not yet read it.
- **Phase B (remaining)**: Any `odoo-*` skills not yet updated will be migrated to add
  Round 0 via the context-bootstrap snippet. Onboard's context becomes the single source
  for project-scoped state.
- **Cross-runtime** (Phase D): Codex and Gemini will read the same `.odoo-ai/context.md` format. The schema is intentionally markdown (not JSON) for portability.
- **Phase E (Visual)**: `.odoo-ai/context.md` is the single source of truth for instance URL and visual config. `/odoo-semantic-skills:setup` writes the `## Instance / Visual` section (instance_base_url, instance_login, visual_mcp, screenshot_baseline_dir); the visual skills (`odoo-ui-reviewer`, `odoo-ui-debug`, `odoo-visual-regression`, `odoo-demo-recorder`) read it at Round 0. Onboard preserves that section across refresh.

## Examples

### Example 1 — Fresh custom distribution repo

User prompt: "I just cloned this Odoo repo — set up context for me"

Skill flow:
1. Pre-flight: no `.odoo-ai/context.md` → continue.
2. Detect root: 12 manifests found under `./` → root inferred as `.`.
3. Version probe: server returns [8.0..19.0]; user picks 17.0.
4. Profile probe: server returns [odoo_17, viindoo_17, ...]; default = viindoo_17 (because `viin_*` prefix detected in Step 4 will run after — for now, ask user).
5. Module discovery: 12 modules; 10 have `viin_` prefix, 2 are `custom_*`.
6. Conventions: prefix=`viin_`, field=`snake_case`, branch=`feature/<slug>`.
7. Pins set: version=17.0, profile=viindoo_17.
8. Write `.odoo-ai/context.md` + add `.gitignore` line.
9. Verify + ask notes.

Output:
```
✓ Onboarding complete

**Project context** saved to `.odoo-ai/context.md`:
- Odoo version: 17.0
- Profile: viindoo_17
- Modules detected: 12 (top: viin_sale_advance, viin_account_vat, viin_purchase_advance)
- Module prefix: viin_
- Lint: ruff line-length=120, JS=web/tooling

`.gitignore` updated to exclude `.odoo-ai/`.

Suggest next: Run `odoo-customization-inventory` to list all 12 modules and assess their business purpose.
```

### Example 2 — Pure Odoo CE repo (no Viindoo)

User prompt: "first time using Odoo for this project — it's a pure Odoo 16 CE deployment"

Skill flow:
1. Pre-flight: no context → continue.
2. Detect root: 3 manifests under `./addons/` → root = `.`.
3. Version probe: user picks 16.0.
4. Profile probe: user picks `odoo_16` (default for pure-Odoo).
5. Module discovery: 3 modules, all prefixed `custom_*`.
6. Conventions: prefix=`custom_`, field=`snake_case`.
7. Pins set: version=16.0, profile=odoo_16.
8. Write context + gitignore.
9. Output suggest-next: default (no special signal in prompt).

### Example 3 — Refresh existing context

User prompt: "initialize Odoo context" (but `.odoo-ai/context.md` already exists, last_updated yesterday)

Skill flow:
1. Pre-flight: context exists, last_updated 2026-05-27 (1 day ago, fresh) → output: "Context already exists (updated 2026-05-27). Refresh? (yes/no)". User says "no" → end.

If user said "yes": continue with full flow, but preserve `## Notes` from existing file.

### Example 4 — Not an Odoo project

User prompt: "set up Odoo for this project" (working dir is a React app, no `__manifest__.py`)

Skill flow:
1. Pre-flight: no context.
2. Detect root: 0 manifests found.
3. Output:

```
No `__manifest__.py` found in working dir or 3 levels down. Is this an Odoo repo?

If yes: provide the project root path (e.g. `/home/user/projects/erp-customer-a`).
If no: this skill is not applicable — try `/odoo-semantic-mcp:connect` to set up the MCP server connection instead (a different scope from project root).
```

Wait for user.

## What this skill does NOT do

- Does NOT install dependencies, run migrations, or modify Odoo source.
- Does NOT auto-discover modules outside working directory (no global filesystem scan).
- Does NOT call MCP write/import tools (only read + session-pin tools).
- Does NOT remember context across machines (file is local to project repo; commit `.gitignore` so other machines don't see context).
- Does NOT replace `/odoo-semantic-mcp:connect` (which sets up the MCP server connection itself — a different scope).

## Notes for future maintainers

- The schema (markdown bullets, not YAML) is intentional for portability across Claude Code / Codex / Gemini.
- Phase B will add Round -1 to all existing skills; until then, context file is harmless if other skills don't read it.
- The 30-day refresh threshold is a guess — adjust based on user feedback. Common refresh triggers: Odoo version upgrade, new custom module added, new team member joins (different conventions).
- Trigger description optimization is scheduled for Phase D via `/skill-creator` Mode 5 with a 20-query trigger eval set (combined with `intake`).
- See the harness reference doc (`docs/reference/workflow-harness.md`) for full design rationale.
