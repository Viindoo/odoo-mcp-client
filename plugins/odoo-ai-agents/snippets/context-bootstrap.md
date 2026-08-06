<!-- SSOT snippet. The single home for the "Round 0 - read project context before asking
     anything" step. Referenced (not copy-pasted) by every skill that needs odoo_version / profile /
     module list / instance URL. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/context-bootstrap.md. Written by the odoo-onboarding skill.
     This snippet's resolve-capture-substitute step (1 below) propagates to every Round 0 in the
     plugin - see ${CLAUDE_PLUGIN_ROOT}/snippets/state-root-resolution.md for the full protocol
     this implements. -->

# Round 0 - Context Bootstrap (read before you ask)

Before asking the caller for any project fact, **read what onboarding already captured.** A
human running `odoo-onboarding` persists `context.md` under the project's Tier-2 SHARE dir; treat
it as authoritative ground truth for this project. Do this first, silently, every run:

1. Resolve the SHARE dir per `snippets/state-root-resolution.md` (the resolve-capture-substitute
   protocol): `Bash: bash ${CLAUDE_PLUGIN_ROOT}/scripts/lib/resolve_project_dir.sh share`, capture
   the printed absolute path, then `Read <captured>/context.md` if present (e.g. captured
   `/home/user/.odoo-ai/projects/ab12cd34ef56` -> `Read
   /home/user/.odoo-ai/projects/ab12cd34ef56/context.md`). Never put `$ODOO_AI_PROJECT_DIR` or a bare
   `.odoo-ai/context.md` literal into the Read call - see the protocol for why. Extract and use as
   defaults:
   - `odoo_version` -> feeds `set_active_version` and every version-sensitive decision.
   - `viindoo_profile` -> feeds `set_active_profile` (never hard-code `standard_viindoo_17`).
   - `modules` / addons path -> the module list; do not ask for it.
   - `instance_base_url` / `instance_login` -> for any live-instance or browser step.
   - `verify_python` (if `## Verify environment` present) -> a non-authoritative HINT for READ-ONLY
     flows only. For ANY odoo-bin / test / migration / DB-mutation run, re-resolve the interpreter
     per `snippets/venv-resolution.md` and confirm it with `<py> <odoo-bin> --version` before use -
     never trust this cache alone for a mutation.
   - `addons_path` (if `## Verify environment` present) -> default addons path for any odoo-bin /
     test / migration run; still re-resolve from instances.toml when a listed repo path no longer
     exists on disk.
   - `doc_output_dir` (optional) -> destination directory for cluster/website documentation produced by `odoo-doc-illustration` (MODE cluster); defaults to `<captured SHARE dir>/visual/doc/` when absent.
2. If the resolved `context.md` is absent (no file at `<captured SHARE dir>/context.md`), derive what you can from disk before asking:
   - version from `find . -maxdepth 4 -name __manifest__.py | head -1` -> `Read` -> `version`
     field (first two dotted components are the Odoo version);
   - module list by globbing manifests; profile inferred from module prefixes
     (`viin_*` -> viindoo profile, otherwise the stock odoo profile).
3. Ask the caller **only** for fields still unresolved after steps 1-2, and batch them into a
   single message - never multi-turn for data that was on disk.

The session-bootstrap tool examples in each skill (`set_active_version(...)`,
`set_active_profile(...)`) are illustrative: their argument values come from this Round 0, not
from the literal placeholder text.
