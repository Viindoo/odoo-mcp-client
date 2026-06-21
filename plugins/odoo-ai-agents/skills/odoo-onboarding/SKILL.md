---
name: odoo-onboarding
description: |
  Bootstrap Odoo project context on first use - probe the Odoo environment (version, custom modules, active profile, naming conventions) and persist findings to `.odoo-ai/context.md` at project root (gitignored), so every later `odoo-*` skill reads it as Round -1 and skips setup.

  Trigger AGGRESSIVELY on "new Odoo project" / "first time" signals, or when no `.odoo-ai/context.md` exists yet: "set up Odoo for this project", "initialize Odoo context". Also fires on Vietnamese: "khởi tạo dự án Odoo mới", "thiết lập context Odoo". Implicit: dir has `__manifest__.py` but no `.odoo-ai/context.md` → first `odoo-*` skill recommends onboard; intake also escalates here when context is missing.

  DO NOT trigger when: (1) `.odoo-ai/context.md` exists and `last_updated` < 30 days - offer "refresh?" instead; (2) no `__manifest__.py` within 3 levels; (3) the user is mid-workflow inside another skill (e.g. odoo-coding writing code) - don't interrupt; (4) the user types another skill's trigger - let that skill fire
---

# Odoo Onboard - Project Context Bootstrap

## Persona

Front door for all Odoo personas (Developer, Pre-Sales, AE, Marketer, CS). Most useful on the FIRST session against a new project repo - once context exists, only refresh on quarterly cadence or major version change.

## Out of Scope

- **NEVER write outside `.odoo-ai/`.** One context file + one `.gitignore` line only.
- **NEVER call MCP write tools.** Only read tools: `list_available_versions`, `list_available_profiles`, `set_active_version`, `set_active_profile`, `check_module_exists`.
- **NEVER assume context without user confirm.** Every detected field must be shown and confirmed before persisting.
- **NEVER overwrite a recent context.** If `last_updated` < 30 days, ask before overwriting.
- **NEVER probe outside the working directory.** Limit `find`/`grep` to cwd + 3 levels deep.

## Onboarding workflow

9 steps; each must pass its success criterion before proceeding.

### Step 0 - Pre-flight

Check `.odoo-ai/context.md`:
- Exists AND `last_updated` < 30 days → "Context already exists (updated \<date\>). Refresh? (yes/no)". No → end. Yes → continue; preserve `## Notes` AND `## Instance / Visual` verbatim (owned by `/odoo-ai-agents:odoo-setup`).
- Exists AND stale (>30 days) → note staleness + continue with refresh.
- Absent → continue.

### Step 1 - Detect project root

```bash
find . -maxdepth 3 -name "__manifest__.py" 2>/dev/null | head -20
```

0 results → "No `__manifest__.py` found. Is this an Odoo repo? Provide the project root path." Wait for user.
≥1 results → infer root (common parent) → continue.

### Step 2 - Probe available Odoo versions

Call `mcp__odoo-semantic__list_available_versions` (no args). Show list; highlight default (prefer 17.0, else highest). Wait for user pick; validate against available list.

### Step 3 - Probe available profiles

Call `mcp__odoo-semantic__list_available_profiles` (no args). Default heuristic:
- No `viin_*` prefix → `odoo_<version>` or null
- ≥1 `viin_*` module → `standard_viindoo_<version>`

Present inferred default; wait for user pick.

Then call `mcp__odoo-semantic__profile_inspect(method='summary', name=<chosen_profile>, odoo_version=<chosen_version>)` to capture real composition (inheritance chain, repos, module count) and record into `.odoo-ai/context.md`. This doubles as validation that the profile name resolves.

### Step 4 - Discover custom modules

```bash
find . -maxdepth 3 -name "__manifest__.py" -exec dirname {} \; | head -50
```

For each path: extract module name + grep `'summary':` from `__manifest__.py`. Build numbered list and show:
> "Detected `<N>` modules. Include all? Or edit list? (yes / list to exclude)"

Wait for user; if excluding, prompt for line numbers or names.

### Step 5 - Extract team conventions

Detect from confirmed module list:
- **module_prefix**: longest common prefix (if multiple competing prefixes, report top-2).
- **field_naming**: assume `snake_case`; override only on user request.
- **vcs_branch_pattern**: try `git log --oneline -20` for naming heuristic; skip if not a git repo.

Detect doc convention for downstream doc/illustration skills:

```bash
# image naming pattern in static/description (e.g. omniapproval_overview.png vs 01-overview.en_US.png)
find . -maxdepth 5 -path "*/static/description/*" \( -name "*.png" -o -name "*.jpg" -o -name "*.gif" \) 2>/dev/null | head -10
# bilingual index files (index_vi_VN.html, index_en_US.html, etc.)
find . -maxdepth 5 -name "index_*.html" 2>/dev/null | head -5
# static/description dir path relative to module root
find . -maxdepth 5 -type d -name "description" 2>/dev/null | head -5
```

From findings derive:
- **doc_image_naming**: regex or prose pattern observed (e.g. `<module>_<feature>.png` or `<N>-<slug>.<locale>.png`). Set `"unknown"` if no images found.
- **doc_languages**: comma-separated locale codes found in bilingual index files (e.g. `en_US,vi_VN`). Omit this field entirely if no bilingual files found (let agent resolve via i18n.json/tier-6).
- **doc_static_dir**: relative path from module root to the description image dir (e.g. `static/description`). Set `"static/description"` as default.

Detect lint/format config for downstream skills:

**Python ruff line-length:**
```bash
grep -m1 'line-length' pyproject.toml ruff.toml 2>/dev/null | head -1
```
Record the value found, or `"none"` if absent. Never assume a default.

**JS config:**
```bash
find . "${ODOO_GIT_BASE:-$HOME/git}" -maxdepth 6 -path "*/addons/web/tooling" -type d 2>/dev/null | head -1
```
If `addons/web/tooling/` found → `"web/tooling"`; else → `"fallback"` (plugin's `scripts/odoo-prettierrc.json`: tabWidth 4, printWidth 100).

Confirm all in one batch:
> "Conventions: prefix=`viin_`, field=`snake_case`, branch=`feature/<ticket>-<slug>`. Lint: ruff line-length=`120`, JS=`web/tooling`. Correct? (yes / edit)"

### Step 6 - Set session pins

Call `mcp__odoo-semantic__set_active_version(odoo_version=<Step 2 value>)`.
Call `mcp__odoo-semantic__set_active_profile(profile_name=<Step 3 value>)` - skip if null.
On failure: log error in `## Notes` and continue.

### Step 7 - Write context file

```bash
mkdir -p .odoo-ai
```

Write `.odoo-ai/context.md` per schema below. On refresh: preserve `## Notes` AND `## Instance / Visual` verbatim.

### Step 8 - Update `.gitignore`

Grep for `.odoo-ai/`; if absent, append (with leading newline if needed). If `.gitignore` missing, create it. Idempotent.

### Step 9 - Verify + suggest next

Show the summary block (Output Format below). Ask: "Anything to add to `## Notes`? (text / skip)". Append if provided, then output the suggest-next line.

Run:

```bash
eval "$(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/lib/instances_io.py read ~/.odoo-ai/instances.toml <series>)"
```

- If the command exits non-zero (no matching instance in instances.toml), skip the `## Verify environment` section entirely - do not block onboarding on it.
- If it exits 0 but `INST_PYTHON` is empty (the `python` field was blank in instances.toml), omit `verify_python` from the section.
- Only write `verify_python` when `INST_PYTHON` is a non-empty path.
- `INST_ADDONS_PATH` uses colon-separated paths (`:`) - convert to comma-separated (`,`) before writing `addons_path` (the schema and Odoo `--addons-path` both expect commas).

## Context file schema

```markdown
# Odoo Project Context

> Generated by `odoo-onboarding` skill on <ISO8601>. Read by all `odoo-*` skills as Round -1 (before Round 0: `set_active_version`).

## Environment
- **odoo_version**: 17.0
- **viindoo_profile**: viindoo_17  (or `null` if pure Odoo)
- **edition**: your Odoo distribution  (one of: CE | EE | custom)

## Custom modules detected
- viin_sale_advance - Sale order advance payments
- viin_account_vat - Vietnam VAT compliance
- custom_loyalty - Customer loyalty program

## Team conventions
- **module_prefix**: viin_
- **field_naming**: snake_case
- **vcs_branch_pattern**: feature/<ticket-id>-<slug>
- **doc_image_naming**: <pattern observed in static/description, e.g. "viin_<module>_<feature>.png"; "unknown" if no images>
- **doc_languages**: <comma-separated locale codes found in bilingual index files, e.g. "en_US,vi_VN"; omit if no bilingual files found>
- **doc_static_dir**: <relative path from module root to description image dir, e.g. "static/description">

## Lint / Format
- **ruff_line_length**: 120  (read from pyproject.toml/ruff.toml; "none" if absent)
- **js_config_source**: web/tooling  (or "fallback" when no Odoo checkout with addons/web/tooling/ is locatable)

## Verify environment  (optional - used by run/verify steps; SSOT is ~/.odoo-ai/instances.toml)
- **verify_python**: /path/to/.venv/bin/python  (interpreter that runs odoo-bin/tests for this series; cache of the matching instances.toml `python` field)
- **addons_path**: /path/repo-a/addons,/path/repo-b  (cache only - re-resolve from instances.toml if a repo moved)

## Active session pins
- **set_active_version**: 17.0 (TTL 24h - re-pin if stale)
- **set_active_profile**: viindoo_17

## Instance / Visual  (optional - populated by /odoo-ai-agents:odoo-setup)
- **instance_base_url**: http://localhost:8069
- **instance_login**: admin  (password NEVER stored here - agreed credential source only)
- **visual_mcp**: chrome-devtools  (the browser MCP wired for the visual skills)
- **screenshot_baseline_dir**: .odoo-ai/visual/baseline
- **brand_tokens_source**: .odoo-ai/brand-tokens.json  (optional - consumer-declared JSON map `token -> color`, e.g. `{"--primary": "#1E88E5"}`; enables the brand-fidelity checks in verify-frontend.sh Tier 4 + ui-reviewer Step 4b. Omit for pure-Odoo projects. No brand is vendored in the plugin.)
- **mockup_dir**: .odoo-ai/mockups  (optional - reference mockups/design specs for the mockup-first fidelity check)

## last_updated
2026-05-28T11:30:00Z

## Notes
<user-provided free-form notes, preserved across refresh>
```

Fields are markdown bullets (not YAML) - human-readable + diff-friendly. Downstream skills parse via `^\s*-\s*\*\*<key>\*\*:\s*(.+)$`.

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

Suggest next: <relevant follow-up - see "Suggest-next logic" below>
```

### Suggest-next logic

Pick ONE:
- Many `viin_*` modules + custom profile → "Run `odoo-customization-inventory`."
- User mentioned "upgrade" / "migration" → "Run `odoo-deprecation-audit` next."
- User mentioned "feature" / "client" → "Try `odoo-feature-check` or `odoo-gap-analysis`."
- Repo has frontend assets OR user mentioned UI/demo/video → "Run `/odoo-ai-agents:odoo-setup` to wire the visual stack."
- Default → "Ready for any `odoo-*` skill. All skills will auto-read `.odoo-ai/context.md`."

## Standalone-first fallback

When OSM (`odoo-semantic-mcp`) is unreachable: still auto-discover modules via disk probes (Steps 1 + 4). For version, read the `version` field from any manifest (first two dotted components) or check `pyproject.toml`/`setup.cfg` before asking. Only ask if no on-disk source resolves it. Write `.odoo-ai/context.md` with `osm_verified: false` so downstream skills know the context is user-asserted.

## Integration notes

- **Context bootstrap**: Many `odoo-*` skills read `.odoo-ai/context.md` via `${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md` at Round 0, pre-filling `odoo_version`, `viindoo_profile`, and module list. Forward-compatible - presence never breaks skills that don't yet read it.
- **Cross-runtime**: Codex and Gemini read the same `.odoo-ai/context.md`. Schema is markdown (not JSON) for portability.
- **Visual stack**: `.odoo-ai/context.md` is SSOT for instance URL and visual config. `/odoo-ai-agents:odoo-setup` writes `## Instance / Visual`; visual skills (`odoo-ui-review`, `odoo-visual-regression`, `odoo-demo-recording`) read it at Round 0. Onboard preserves that section on refresh.

## Examples

See `${CLAUDE_PLUGIN_ROOT}/skills/odoo-onboarding/references/examples.md` for 4 worked examples (fresh repo, pure CE, refresh, non-Odoo project).

## What this skill does NOT do

- Does NOT install dependencies, run migrations, or modify Odoo source.
- Does NOT auto-discover modules outside cwd (no global filesystem scan).
- Does NOT call MCP write/import tools (only read + session-pin tools).
- Does NOT remember context across machines (file is local; commit `.gitignore`).
- Does NOT replace `/odoo-semantic-mcp:connect` (sets up MCP server connection - different scope).

## Continuation Contract

When you finish, append a Continuation Contract block per
`${CLAUDE_PLUGIN_ROOT}/snippets/continuation-contract.md` (status / produced / next). Additive
output for the run-driver - it does not change anything produced above.
