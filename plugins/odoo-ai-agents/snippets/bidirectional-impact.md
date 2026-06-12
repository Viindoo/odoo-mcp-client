<!-- SSOT snippet. Referenced (not copy-pasted) by every agent that designs, writes, reviews, or
     debugs an Odoo change (architect, coder, frontend-coder, code-reviewer, ui-reviewer,
     backend-debugger, ui-debugger). Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/bidirectional-impact.md. -->

# Bidirectional Impact Analysis (both directions, direct + indirect)

An Odoo module is a node in a dependency DAG. A change is never confined to the file you edit: it
ripples **up** (the modules you depend on encode assumptions you might violate) and **down** (the
modules that depend on you inherit your behavior and can break). Before you touch a module - to
design, code, review, or diagnose it - map BOTH directions, **direct and indirect (transitive)**,
and account for every affected node. "I only changed this one file" is how integration bugs are
born at runtime instead of at design time.

## Upstream (what this module depends ON)

Walk the `depends` closure - direct AND transitive:

- `module_inspect(name=<module>, method='dependencies', odoo_version='<concrete>')`; recurse for the
  indirect layer. Fallback when OSM is thin: read each `__manifest__.py` `depends` from disk.
- Ask: does my new field / override / schema / asset change violate a contract the upstream module
  encodes (a field it expects, an MRO order, an asset-bundle it owns, a hook signature)? An
  override only composes safely if it respects what the chain below it already does.

## Downstream (what depends ON this module)

Walk the reverse closure - direct AND transitive:

- `impact_analysis(entity_type='model'|'field'|'method', entity_name='<model[.field|.method]>',
  odoo_version='<concrete>')` on the changed module/model/field to surface dependents (other
  computes, views, reports, overrides) across the graph; read it transitively, not just the first
  ring.
- Ask: could this change break a module that extends mine - a stored compute it relies on, a view
  it `xpath`-es into, a method it `super()`s, a record it references?

## UI axis (frontend agents)

For JS/OWL/QWeb/SCSS work the dependency axis is the **asset bundle and template inheritance**
graph, not the ORM: which modules inherit the QWeb template you change, patch the OWL component,
or load the asset bundle you touch. Same two-direction rule, different graph.

## Record the result

For each affected node in either direction, log it with its mitigation in the worklog
(`worklog-contract.md`): `FLAGGED | <module> ripple: <what> | WHY: <upstream/downstream> | EVIDENCE:
impact_analysis / module_inspect citation`. A design/review/fix that names the blast radius and its
mitigations is gate-able; one that doesn't is a guess.
