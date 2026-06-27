<!-- SSOT for the deep-survey per-phase analytical lenses + drill procedures.
     The orchestrator (opus, main context) reads the lens block relevant to a phase
     and INLINES it into each dispatched worker brief - workers are leaf subagents
     that cannot resolve ${CLAUDE_PLUGIN_ROOT} themselves (same paste mechanism as
     worker-brief.md / bidirectional-impact.md). Edit lenses here, not in SKILL.md. -->

# Deep-Survey Analytical Lenses (worker mandates)

OSM-first on every lens: name OSM tools by PRINCIPLE, pass a **concrete** `odoo_version` on
every call, read raw source only when OSM is silent (then label the finding
`grounded: local-source`). Each lens states what to PRODUCE so a later execute agent acts
without re-deriving. Grounding vocabulary, carried on every finding: `osm` = OSM-grounded,
`hybrid` = OSM + local source, `local-source` = read from disk because OSM was insufficient.

---

## Phase 1 lenses (haiku - wide / shallow, single-tool lookup only)

### L1. Module purpose

Call `describe_module` to capture WHY the module exists in 1-2 lines. Feeds hot-spot ranking:
a hot-spot in a module whose purpose is unrelated to the intent is downgraded before any sonnet
time is spent on it.

### L2. Entry-point map (Odoo-specific, first-class artifact)

Enumerate the surfaces from which execution STARTS - where a downstream change is triggered and
observed, so the consumer needs them named up front. Odoo entry-point classes:

- act_window / server / client actions (`ir.actions.*`)
- HTTP controllers (`route=`)
- scheduled actions (`ir.cron`)
- view-exposed object buttons (`type="object"`, `name=`) and onchanges
- `@api.model` / public methods reachable from JS via `execute_kw`

Ground via `module_inspect` (its actions / controllers view) + `describe_module`; skim
`controllers/` and view button `name=` on disk only when OSM is thin. Output an **Entry points**
bullet list, each with `file:line` + the model / route it dispatches to.

---

## Phase 2 lenses (sonnet - narrow / deep, multi-tool OSM synthesis allowed)

For each hot-spot, apply these lenses and record each as a labelled subsection in the phase2 file.

### L3. Data-flow transformation trace

Trace the value path end-to-end and name each hop + its transformation:
`entry-point -> method -> compute / onchange / constraint -> stored field`. Use
`resolve_orm_chain` for ORM traversal and `find_override_point` to catch interceptors (onchange,
constraint, override) that mutate the value on the path. Output one line plus the interceptors:
`Data flow: A -> B -> C -> stored field X`.

### L4. Abstraction-layer labels

Tag every component the trace touches with its Odoo layer so the downstream agent instantly knows
which tier it stands on:

- `[LAYER: controller]` route / HTTP
- `[LAYER: action/wizard]` ir.actions / TransientModel
- `[LAYER: business-logic]` model method (`action_*`, `_process_*`)
- `[LAYER: compute]` computed field + its `@api.depends`
- `[LAYER: data]` stored column / `_auto=False` SQL view

Example: `[LAYER: business-logic] sale.order.action_confirm -> [LAYER: compute] _amount_all ->
[LAYER: data] amount_total`.

### L5. Side-effects

Note the Odoo-specific side-effects the hot-spot triggers - a change here ripples past the return
value: `mail.thread` message_post / activity, `ir.attachment` create, action redirect,
`stock.move` / accounting-entry generation, `ir.cron` queue, `bus` notification, external API
call. Ground by `find_examples` for the side-effect call pattern, or raw-source grep when OSM is
silent. Output a **Side effects** subsection (or "none observed").

### L6. Cross-cutting (FLAG-ONLY - no overlap with security-audit)

List the security / transaction seams the hot-spot crosses - EXISTENCE only, never a verdict (the
full audit is `odoo-security-audit`): `groups=` on the method / field, `sudo()` calls + the
one-line reason, `@api.constrains` that intersects the hot-spot. Use `model_inspect` (methods
view). Output a **Cross-cutting** subsection.

### L7. Prior art + existing patterns (anti-reinvention - the reason this lens exists)

Before the downstream agent writes anything, tell it what already solves this so it ADAPTS, not reinvents:

- `find_examples` - existing implementations of this pattern in core / Viindoo / custom code.
- `suggest_pattern` - the recommended approach for this kind of change.
- `entity_lookup` - resolve an arbitrary symbol (class / method / field signature) when
  `model_inspect` is not enough.

Output a **Prior art** subsection: each existing override / pattern / test with `file:line` + OSM
citation, and name the ONE the downstream agent should adapt rather than rebuild. A MISS (no prior
art found) is itself a recorded result - it tells the consumer this really is greenfield.

### L8. Tech-debt signals (FLAG-ONLY - do not fix)

Flag, never fix, pre-existing smells a downstream change would inherit: N+1
(`for r in self: r.x = sum(...)` on a high-volume model), deprecated API (`find_deprecated_usage`),
missing `@api.model` on a method called from JS, dangerous `ondelete='cascade'`, other
anti-patterns. Output a **Tech debt** subsection so the downstream coder is not surprised mid-change.

### L9. Per-hot-spot test-protection

After bidirectional impact resolves, determine which tests guard this hot-spot (the test blast
radius). Record tier (i) own-module + tier (ii) dependency tests for the hot-spot's model / view
here; the framework-validation gates (tier iii) are assembled at synthesis. Full three-tier
structure: § Test-protection map below.

---

## Dependency-closure drill (nearest -> base)

Goal: for each hot-spot's external / core symbols, walk the `depends` graph DOWN from the nearest
owning module to `base`, so the downstream agent knows every layer a change rests on - not just the
top ring. The systematic transitive grounding the bidirectional-impact upstream walk only sketches.

**PHASED - never swallow the whole tree at once** (respect the Mode B budget):

1. **Wave 0 - nearest.** The module that directly owns the hot-spot symbol. `module_inspect`
   (dependencies view) + `describe_module`.
2. **Wave 1..n - expand toward base.** Walk the closure one layer at a time: `module_inspect`
   dependencies recursively, or read each `__manifest__.py` `depends` when OSM is thin. Stop a
   branch at `base` or when it leaves the intent's blast radius.
3. **Per-symbol grounding** for the hot-spot's external symbols: REUSE
   `${CLAUDE_PLUGIN_ROOT}/snippets/fp-symbol-survival-check.md` § 2 (per-symbol grounding) + § 2.5
   (the seven autosilent symbol classes) BY PATH - the orchestrator reads that snippet and inlines
   § 2 + § 2.5 into this worker brief; do NOT copy its steps here. Ground at the CURRENT version
   (deep-survey is general-intent). If the intent is upgrade-adjacent, ground at the TARGET version
   instead - the drill then doubles as a pre-upgrade symbol-survival check and feeds
   `upgrade_symbol_gaps` in the synthesis.
4. `validate_depends` to confirm the manifest `depends` actually covers the symbols the module
   pulls (a missing dep is a hot-spot of its own).

Output a **dependency-closure map** - one row per layer:
`module | layer-distance (nearest=0 ... base) | why it matters to the hot-spot | grounded: osm|hybrid|local-source`.

A deep closure (>=3 transitive layers no single worker fully traced) is a Phase-3 escalation knot.

---

## Test-protection map (three tiers)

For every model / view the scope touches, assemble what would CATCH a change - so design / code
knows "touch this -> that test fires":

**Methodology (SSOT):** follow `${CLAUDE_PLUGIN_ROOT}/snippets/test-protection-contract.md` for
the three-tier protocol and the OSM tools to use for each tier. Do not restate tier definitions or
tool names here.

**Survey output** (per model/view, into the `tests_protecting` section of `synthesis.md`):
- Tier (i) + (ii): list each test file path + method name; note "0 found - risk multiplier" when
  no feature coverage exists for that entity.
- Tier (iii): list the framework gates from the parity checklist that apply to this scope; label
  each "framework gate, verify live".
