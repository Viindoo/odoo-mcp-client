# frontend-coder rounds - per-era workflow detail

Round-by-round procedure of the `odoo-frontend-coder` agent for the two frontend eras. The agent
holds the hard rules, Round 0, Round 6 (the static verify gate), the adapt dispositions and the
output format; it points here after the version gate. Read ONLY the section of the era you resolved.

**Contents:** Legacy workflow - OWL workflow

## Legacy workflow

**Round 1 - version check + real examples (parallel).** Fire both:
- `api_version_diff(symbol=<symbol>, from_version="8.0", to_version="<N>.0")` - breaking JS API changes vs the v8 baseline (skip for v8/v9).
- `find_examples(query="<user feature> widget pattern Odoo <N>", odoo_version='<version>')` - real indexed code for the closest matching pattern.

**Round 2 - find override point (only when patching an existing widget).** `find_override_point(model="<WidgetClass>", method="<method>", odoo_version='<version>')` reveals the exact class path + override chain. Skip if Round 0 `module_inspect` already surfaced the path, or for greenfield creation.

**Round 3 - write the boilerplate.** Write the legacy JS for Odoo v<N> using the right pattern (`odoo.define` / `AbstractField` / `Widget.include`), grounded in the Rounds 1-2 examples + API diff. Use the `find_examples` snippets as the structural template so import paths and lifecycle hooks match the target version.

**Round 4 - assemble complete output.** JS file with full `odoo.define()` module · QWeb2 XML template · registration in `<descriptor>` per the agent's Workflows asset rule (Round 0 step 8 resolves the descriptor filename, boundary `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-era-boundaries.md` row 6; edit the one it has, create neither).

**Round 5 - suggest visual verification (forward-wiring).** After presenting, add the `next:` entry per the agent's § Continuation Contract.

## OWL workflow

**Round 0.5 - OWL pitfall grounding checklist (gate).** Before emitting any OWL/JS, assert each class from `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md` ("OWL pitfall catalogue") is satisfied for the target version:
- [ ] **t-on handlers** - no bare free-identifier arrow call (`() => onFoo()`); use `() => this.onFoo()`, the auto-bound `t-on-click="onFoo"`, or `onChange.bind="onFoo"` for props.
- [ ] **useService reactivity** - the wrapping differs per series: copy the target series' form from `find_examples(query='useService useState', odoo_version='<version>')`.
- [ ] **No raw `contenteditable`** - delegate to `web_editor` Wysiwyg, lazy-loaded in `onWillStart`, with stable props built once.
- [ ] **SCSS in `calc()`** - interpolate Sass functions: `calc(#{map-get(...)} * 2)`, never bare `map-get(`/`min(` inside `calc(`.
- [ ] **No `--bs-*` assumptions** - Odoo sets `$variable-prefix:''`; reference `--primary`/`--o-color-*`, never a self-referential shim.
- [ ] **`Dialog` body** - body content goes in the default slot; only `header`/`footer` are named slots.
- [ ] **Inherited QWeb templates** - an xpath into a `t-if`/`t-elif` -> `t-elif`/`t-else` chain follows `${CLAUDE_PLUGIN_ROOT}/skills/_shared/coding_guidelines/<version>/xml.md` § Inheriting QWeb templates (Round 6 BLOCKs a `before`/`after` that splits the chain).

**Round 1 - detect OWL sub-version (parallel when porting).** The `patch()` form per version is the agent's § Version gate table; lifecycle hooks come from `@odoo/owl` in every OWL version. The series is the one Round 0 resolved (`${CLAUDE_PLUGIN_ROOT}/snippets/project-facts-resolution.md`); never assume one. If porting between versions, call `api_version_diff` to surface breaking changes first.

**Round 2 - discover existing components + gather examples (parallel, all independent):**
1. `module_inspect(name=<module>, method='owl', odoo_version='<version>')` - enumerate OWL components; check naming collisions.
2. `module_inspect(name=<module>, method='qweb', odoo_version='<version>')` - enumerate QWeb template IDs; verify the exact template name before writing XPath overrides.
3. `find_examples(query="OWL component <feature> Odoo v<N>", odoo_version='<version>')` - real import paths and hook names (trust this over training memory for syntax).
4. `find_override_point(model=<Component>, method=<method>, odoo_version='<version>')` - only when patching an existing component; skip for brand-new ones.

Confirm currency of every core registry/service/hook API you call at the target version by the agent's § Workflows JS currency authority: `api_version_diff(symbol='<symbol>', from_version='<older>', to_version='<version>')` when the code crosses versions, plus `find_examples(query='<hook/registry usage>', odoo_version='<version>')` for real indexed usage AT the target.

**Round 3 - write the component.** Write the OWL `<1.x|2.x>` component - `setup()` + lifecycle hooks + template, any `patch()` block, and the `registry.category('…').add(…)` registration - grounded in the Rounds 1-2 example snippets, registry category, and verified import paths. Reason step by step before writing when: logic crosses multiple components via `useChildSubEnv`/`useBus`; a custom service holds state surviving unmount; or a `patch` must call `super` at a position-sensitive point relative to side effects.

**Round 4 - assemble complete output.**

**Before emitting the first code block**, write a "**VERSION RULES APPLIED (v<N>):**" block listing the key pivot rules for the JS/OWL/SCSS you will write (e.g. "JS module header: per F0 §JavaScript/OWL/tests; OWL patch form: per the agent's Version gate table; SCSS: no `--bs-*` tokens") drawn from `odoo-version-pivots.md` and `odoo-frontend-fidelity.md`. Anti-compaction sticky note; `odoo-code-reviewer` WILL verify each cited rule against the actual code.

1. **JS file** - `/** @odoo-module **/` first line per `${CLAUDE_PLUGIN_ROOT}/snippets/odoo-version-pivots.md` §JavaScript/OWL/tests row "JS module header" (and `${CLAUDE_PLUGIN_ROOT}/skills/_shared/odoo-frontend-fidelity.md`), then `import`s from verified paths, then the component class, then registry `.add()`.
2. **XML template file** - separate file preferred for templates over ~10 lines.
3. **Manifest assets block** - register per the agent's Workflows asset rule.
4. **OWL version notes** - briefly note any 1.x→2.x differences relevant to the generated code.
