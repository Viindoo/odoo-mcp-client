<!-- SSOT snippet. Factored from odoo-solution-architect § Module ownership and dependency
     integrity. Referenced (not copy-pasted) by odoo-solution-architect and by child-architect
     workers in master-child runs. Edit here only; consumers point at
     ${CLAUDE_PLUGIN_ROOT}/snippets/module-ownership-contract.md. -->

# Module Ownership and Dependency Integrity

Where functionality LIVES is a deliberate first-class design decision, not the most convenient
placement. For every feature: identify the module that owns the business responsibility, the
module containing the implementation, all involved existing modules, whether an integration module
is needed, whether new dependencies are valid, and whether existing tools/methods/fields/models/
views in the dependency chain already provide coverage.

## Dependency direction (hard rules - never violate)

- A base module must not depend on a higher-level business module.
- A reusable module must not depend on any of its consumers.
- Independent modules must not couple without clear justification.
- No circular deps, direct or indirect.
- References to models/fields/methods/XML IDs/security groups/business concepts come only from
  valid declared dependencies.

## Choosing the module

For functionality related to module `X`, do not auto-place it in `X`. Evaluate: `X` itself vs a
direct dep vs an indirect dep vs a shared reusable module vs a dedicated integration module.
Prefer the LOWEST architectural layer that logically owns the responsibility. Functionality
spanning multiple modules belongs in a dedicated integration module, an extension module that
depends on all required modules, or a reusable abstraction in a shared dep - not split across
modules at the same layer without a clear ownership boundary.

## Odoo CE/EE policy

CE/EE repos are for bug fixes only - never new business functionality. New business logic goes in
the appropriate custom module or integration module. If a CE/EE bug blocks the solution, document
it and propose the minimal upstream fix only when necessary for the solution to function.

## Validation gate (answer all before the design ships)

1. Which module owns this responsibility, and why?
2. Are all dependency directions valid (no up-dep, no circular)?
3. Can this move to a lower layer without losing clarity?
4. Would a dedicated integration module be cleaner than coupling two existing modules?
5. Does each new module have a single clear business intent?

A solution that works but is assigned to the wrong module, violates dependency direction, or
weakens architectural boundaries is an INCOMPLETE design.
