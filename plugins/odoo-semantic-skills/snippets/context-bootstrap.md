<!-- SSOT snippet. The single home for the "Round 0 - read project context before asking
     anything" step. Referenced (not copy-pasted) by every skill that used to ask the user for
     odoo_version / profile / module list / instance URL. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md. Written by the odoo-onboard skill. -->

# Round 0 - Context Bootstrap (read before you ask)

Before asking the caller for any project fact, **read what onboarding already captured.** A
human running `odoo-onboard` persists `.odoo-ai/context.md`; treat it as authoritative ground
truth for this project. Do this first, silently, every run:

1. `Read .odoo-ai/context.md` if present. Extract and use as defaults:
   - `odoo_version` -> feeds `set_active_version` and every version-sensitive decision.
   - `viindoo_profile` -> feeds `set_active_profile` (never hard-code `viindoo-internal`).
   - `modules` / addons path -> the module list; do not ask for it.
   - `instance_base_url` / `instance_login` -> for any live-instance or browser step.
2. If `.odoo-ai/context.md` is absent, derive what you can from disk before asking:
   - version from `find . -maxdepth 4 -name __manifest__.py | head -1` -> `Read` -> `version`
     field (first two dotted components are the Odoo version);
   - module list by globbing manifests; profile inferred from module prefixes
     (`viin_*` -> viindoo profile, otherwise the stock odoo profile).
3. Ask the caller **only** for fields still unresolved after steps 1-2, and batch them into a
   single message - never multi-turn for data that was on disk.

The session-bootstrap tool examples in each skill (`set_active_version(...)`,
`set_active_profile(...)`) are illustrative: their argument values come from this Round 0, not
from the literal placeholder text.
