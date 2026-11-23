# The SRS - what it holds, what it leaves to the design

The SRS states the problem as its roles see it: their jobs, the business rules, the outcomes they
can observe. The business owner approves it and every later step tests against it. The design
states the solution.

## The line between the SRS and the design

One test per sentence: would it change if the code were written another way while the behaviour
stayed the same? Then it belongs to the design.

- **In the SRS:** a role and its job; a business rule; an outcome a role observes; a screen, menu
  or report named by its label; a module as the unit a customer installs, by its label, with its
  technical name once in Scope; what an existing database still holds and does after the update.
- **In the design, never in the SRS:** a model, field, method, view or record id; a file; an
  inheritance or override choice; which module owns a symbol; how an update gets there (a
  migration script, a hook); a commit, build or delivery step; a source citation.
- A technical fact found while writing the SRS goes to the worklog; the design cites it under
  `## Grounding evidence`.
- A change that keeps behaviour (an upgrade, a port, a refactor) has a short SRS: the behaviour
  that must survive, per role, and the criteria that prove it, each comparing one observable
  result before and after.

## Template

```
# SRS - <change name>
Domain: <business_function>; Audience: <roles | n/a>; Outcome: <business result>
Odoo version: <v>   Profile: <p>   Effort: Standard | Config | Extension | Extension-L | Custom-XL

## Roles and their jobs        (per role: what the role does today, what changes for them)
## Scope                       (the capabilities in and those explicitly out; the modules as
                                products)
## Business rules              (one id each; a rule a law sets goes under Legal rules as data)
## Interactions                (`A -> B: <business result>` per cross-function interaction)
## Non-functional              (what a role or an operator can observe: companies and branches,
                                languages, volumes, who may see what, what an upgrade must keep,
                                the countries served)
## Management insight          (${CLAUDE_PLUGIN_ROOT}/snippets/management-insight.md § At design)
## Demo data                   (the business situations a demo must show)
## Legal rules as data         (only when a law or regulation sets a value or rule the change
                                touches: per element, the four questions of
                                odoo-platform-design-principles.md § 6)
## Acceptance criteria         (per role or flow, never per module: an id, Given / When / Then
                                and the expected VALUE)
```

The Domain line follows `${CLAUDE_PLUGIN_ROOT}/snippets/business-taxonomy.md`. Effort follows
`GAP_MATRIX` when given.

The acceptance criteria are the acceptance oracle
(`${CLAUDE_PLUGIN_ROOT}/snippets/acceptance-oracle-contract.md`). Each names its acting role and
one comparable value: hand-computed for a calculation; read from the index or the source for
behaviour that exists without the change (who may open a screen, what a core control does, which
transitions core allows); never taken from the code of the change. The design maps each id to
the unit that satisfies it.
